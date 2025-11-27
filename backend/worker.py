"""
Celery worker configuration and tasks.
"""
import asyncio
import logging
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select, func
from sqlalchemy.orm.attributes import flag_modified

from backend.core.config import settings
from backend.core.logging_handler import LoggingContext
from backend.models.base import AsyncSessionLocal
from backend.models.backup import (
    Backup,
    BackupSchedule,
    Job,
    JobLog,
    JobType,
    JobStatus,
    BackupStatus,
    SourceType
)
from backend.services.kvm.backup import KVMBackupService
from backend.services.podman.backup import PodmanBackupService
from backend.services.storage import create_storage_backend
from backend.services.retention.policy import RetentionPolicy
from backend.services.verification import RecoveryTestService
from backend.services.progress import create_tracker, remove_tracker

logger = logging.getLogger(__name__)


async def log_job_verbose(db, job_id: int, level: str, message: str, details: dict = None):
    """
    Create a verbose job log entry with optional structured details.

    This helper function should be called for every significant operation during
    job execution to provide comprehensive logging for debugging and monitoring.

    Args:
        db: Database session
        job_id: ID of the job
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Human-readable log message
        details: Optional structured metadata (e.g., command details, progress, etc.)
    """
    from backend.models.backup import JobLog
    log = JobLog(
        job_id=job_id,
        level=level,
        message=message,
        details=details
    )
    db.add(log)
    await db.flush()  # Use flush instead of commit for batching


# Initialize Celery
celery_app = Celery(
    "lab_backup",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_track_started=settings.CELERY_TASK_TRACK_STARTED,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "check-scheduled-backups": {
        "task": "backend.worker.check_scheduled_backups",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    "backup-database": {
        "task": "backend.worker.backup_database",
        "schedule": crontab(hour="1", minute="0"),  # Daily at 1 AM
    },
    "apply-retention-policies": {
        "task": "backend.worker.apply_retention_policies",
        "schedule": crontab(hour="2", minute="0"),  # Daily at 2 AM
    },
    "cleanup-expired-backups": {
        "task": "backend.worker.cleanup_expired_backups",
        "schedule": crontab(hour="3", minute="0"),  # Daily at 3 AM
    },
    "cleanup-logs": {
        "task": "backend.worker.cleanup_logs",
        "schedule": crontab(hour="4", minute="0"),  # Daily at 4 AM
    },
    "update-storage-usage": {
        "task": "backend.worker.update_storage_usage",
        "schedule": crontab(hour="*/6", minute="0"),  # Every 6 hours
    },
    "weekly-backup-verification": {
        "task": "backend.worker.verify_recent_backups",
        "schedule": crontab(day_of_week="0", hour="5", minute="0"),  # Every Sunday at 5 AM
    },
    "calculate-compliance": {
        "task": "backend.worker.calculate_compliance",
        "schedule": crontab(minute="0"),  # Every hour on the hour
    },
    "send-daily-compliance-summary": {
        "task": "backend.worker.send_daily_compliance_summary",
        "schedule": crontab(hour="7", minute="0"),  # Daily at 7 AM
    },
}


@celery_app.task(name="backend.worker.execute_backup")
def execute_backup(schedule_id: Optional[int], backup_id: int):
    """
    Execute a backup job.

    Args:
        schedule_id: ID of the backup schedule (None for one-time backups)
        backup_id: ID of the backup record
    """
    # Create a new event loop for this task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(_execute_backup_async(schedule_id, backup_id))
    finally:
        loop.close()


async def _execute_backup_async(schedule_id: Optional[int], backup_id: int):
    """Async implementation of backup execution."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    # Create a new async engine for this event loop
    engine = create_async_engine(
        str(settings.DATABASE_URL),
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with SessionLocal() as db:
        backup = None
        job = None
        try:
            # Get backup
            backup = await db.get(Backup, backup_id)
            if not backup:
                raise Exception("Backup not found")

            # Get schedule if this is a scheduled backup
            schedule = None
            if schedule_id:
                schedule = await db.get(BackupSchedule, schedule_id)
                if not schedule:
                    raise Exception("Schedule not found")

            # Find existing PENDING job created by API endpoint
            stmt = select(Job).where(
                Job.celery_task_id == celery_app.current_task.request.id
            )
            result = await db.execute(stmt)
            job = result.scalar_one_or_none()

            if not job:
                # If no job exists (shouldn't happen), create one
                job_metadata = {"schedule_id": schedule_id} if schedule_id else {"one_time": True}
                job = Job(
                    type=JobType.BACKUP,
                    status=JobStatus.RUNNING,
                    backup_id=backup_id,
                    started_at=datetime.utcnow(),
                    celery_task_id=celery_app.current_task.request.id,
                    job_metadata=job_metadata
                )
                db.add(job)
            else:
                # Update existing job to RUNNING
                job.status = JobStatus.RUNNING
                job.started_at = datetime.utcnow()

            await db.commit()

            # Set logging context for this job (wraps all operations with job_id and backup_id)
            with LoggingContext(job_id=job.id, backup_id=backup_id):
                # Update backup status
                backup.status = BackupStatus.RUNNING
                backup.started_at = datetime.utcnow()
                await db.commit()

                # Log start
                backup_type_str = f"{backup.backup_mode.value} backup" if hasattr(backup, 'backup_mode') else "backup"
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message=f"Starting {backup_type_str} of {backup.source_type} {backup.source_name}"
                )
                db.add(log)
                await db.commit()

                # Execute backup based on source type
                if backup.source_type == SourceType.VM:
                    result = await _backup_vm(db, schedule, backup, job)
                elif backup.source_type == SourceType.CONTAINER:
                    result = await _backup_container(db, schedule, backup, job)
                else:
                    raise Exception(f"Unknown source type: {backup.source_type}")

                # Update backup with results
                backup.status = BackupStatus.COMPLETED
                completed_time = datetime.utcnow()
                backup.completed_at = completed_time
                backup.size = result.get("original_size", 0)
                backup.compressed_size = result.get("compressed_size", 0)
                backup.storage_path = result.get("storage_path")
                backup.checksum = result.get("checksum")

                # Capture storage encryption metadata (Issue #12)
                if result.get("storage_encryption_type"):
                    backup.storage_encryption_type = result.get("storage_encryption_type")
                    backup.storage_encryption_key_id = result.get("storage_encryption_key_id")
                    logger.info(
                        f"Backup {backup.id} uses {backup.storage_encryption_type} encryption"
                    )
                elif backup.encryption_key_id:
                    # App-level encryption was used
                    backup.storage_encryption_type = "APP_LEVEL"

                # Initialize backup chain tracking (Issue #10)
                try:
                    from backend.services.backup_chain import BackupChainService
                    chain_service = BackupChainService(db)
                    await chain_service.initialize_backup_chain(
                        backup=backup,
                        backup_mode=backup.backup_mode,
                        original_size=result.get("original_size"),
                        deduplicated_size=result.get("deduplicated_size")
                    )
                    logger.info(
                        f"Initialized backup chain for backup {backup.id}: "
                        f"chain_id={backup.chain_id}, sequence={backup.sequence_number}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to initialize backup chain: {e}")

                # Update job
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()

                # Update last_successful_backup for compliance tracking (Issue #8)
                try:
                    from backend.services.compliance import ComplianceService
                    compliance_service = ComplianceService(db)
                    await compliance_service.update_last_successful_backup(
                        source_type=backup.source_type,
                        source_id=backup.source_id,
                        completed_at=completed_time
                    )
                except Exception as e:
                    logger.warning(f"Failed to update compliance tracking: {e}")

                # Log completion
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message=f"Backup completed successfully. Size: {backup.compressed_size} bytes"
                )
                db.add(log)

                await db.commit()

                return {
                    "success": True,
                    "backup_id": backup_id,
                    "size": backup.compressed_size
                }

        except Exception as e:
            # Set logging context for error handling
            with LoggingContext(job_id=job.id if job else None, backup_id=backup_id):
                # Update backup status
                if backup:
                    backup.status = BackupStatus.FAILED
                    backup.error_message = str(e)
                    backup.completed_at = datetime.utcnow()

                # Update job
                if job:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)
                    job.completed_at = datetime.utcnow()

                    # Log error
                    log = JobLog(
                        job_id=job.id,
                        level="ERROR",
                        message=f"Backup failed: {str(e)}"
                    )
                    db.add(log)

                await db.commit()

                return {
                    "success": False,
                    "error": str(e)
                }
        finally:
            # Dispose engine to clean up connections
            await engine.dispose()


async def _backup_vm(db, schedule, backup, job):
    """Execute VM backup."""
    from backend.models.infrastructure import VM, KVMHost

    # Get VM and host (use backup.source_id for both scheduled and one-time backups)
    vm = await db.get(VM, backup.source_id)
    if not vm:
        raise Exception(f"VM with ID {backup.source_id} not found")

    kvm_host = await db.get(KVMHost, vm.kvm_host_id)
    if not kvm_host:
        raise Exception(f"KVM host not found for VM {vm.name}")

    # Log
    log = JobLog(
        job_id=job.id,
        level="INFO",
        message=f"Connecting to KVM host: {kvm_host.name}"
    )
    db.add(log)
    await db.commit()

    # Create temp directory for backup
    with tempfile.TemporaryDirectory() as temp_dir:
        backup_dir = Path(temp_dir) / f"vm_{vm.name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Create a list to collect logs from the KVM service (runs in executor thread)
        # These will be persisted after the backup completes
        pending_logs = []

        def kvm_log_callback(level: str, message: str, details: dict = None):
            """Callback to capture verbose logs from KVM service."""
            # Append to pending logs list - will be persisted after backup
            pending_logs.append({
                "level": level,
                "message": message,
                "details": details,
                "timestamp": datetime.utcnow()
            })

        # Execute backup with verbose logging callback
        kvm_service = KVMBackupService(log_callback=kvm_log_callback)

        # Setup authentication for KVM host if using password auth
        await kvm_service.setup_auth_for_host(db, kvm_host.id)

        # Determine backup mode (full vs incremental) - Issue #15
        from backend.models.backup import BackupMode

        # Get schedule's incremental configuration if this is a scheduled backup
        backup_mode_policy = "auto"
        max_chain_length = 14
        parent_checkpoint = None
        is_incremental = False

        if schedule:
            backup_mode_policy = getattr(schedule, 'backup_mode_policy', 'auto')
            max_chain_length = getattr(schedule, 'max_chain_length', 14)
            parent_checkpoint = getattr(schedule, 'checkpoint_name', None)

        # Determine current chain length
        chain_length = 0
        from sqlalchemy import func as sa_func, and_
        if schedule and schedule.last_full_backup_id:
            # Count incrementals since last full (scheduled backups)
            chain_count_stmt = select(sa_func.count(Backup.id)).where(
                and_(
                    Backup.schedule_id == schedule.id,
                    Backup.id > schedule.last_full_backup_id,
                    Backup.backup_mode == BackupMode.INCREMENTAL
                )
            )
            result = await db.execute(chain_count_stmt)
            chain_length = result.scalar() or 0
        elif backup.parent_backup_id:
            # One-time incremental backup - count chain from parent
            # Find the chain by traversing up to the full backup
            parent = await db.get(Backup, backup.parent_backup_id)
            if parent and parent.chain_id:
                # Count backups in the chain
                chain_count_stmt = select(sa_func.count(Backup.id)).where(
                    Backup.chain_id == parent.chain_id
                )
                result = await db.execute(chain_count_stmt)
                chain_length = result.scalar() or 0
            elif parent:
                # Parent exists but no chain_id - at minimum we have 1 backup
                chain_length = 1

        # Determine whether to use incremental backup
        mode_decision = await kvm_service.determine_backup_mode(
            uri=kvm_host.uri,
            vm_uuid=vm.uuid,
            schedule_policy=backup_mode_policy,
            chain_length=chain_length,
            max_chain_length=max_chain_length,
            force_full=backup.backup_mode == BackupMode.FULL if hasattr(backup, 'backup_mode') else False
        )

        is_incremental = mode_decision["mode"] == "incremental"
        incremental_method = mode_decision.get("incremental_method")

        log = JobLog(
            job_id=job.id,
            level="INFO",
            message=f"Backup mode decision: {mode_decision['mode']} ({mode_decision['reason']})"
        )
        db.add(log)
        await db.commit()

        # Check if CBT (Changed Block Tracking) should be used (Issue #15)
        use_cbt = False
        use_checkpoint_api = False

        # RBD-native incremental backup flag
        use_rbd_native = False

        if is_incremental:
            if incremental_method == "rbd_native":
                use_rbd_native = True
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message="Using RBD-native incremental backup (export-diff)"
                )
                db.add(log)
                await db.commit()
            elif incremental_method == "checkpoint":
                use_checkpoint_api = True
                use_cbt = True
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message=f"Using libvirt checkpoint API for incremental backup (parent: {parent_checkpoint or 'new chain'})"
                )
                db.add(log)
                await db.commit()
            elif vm.cbt_enabled and vm.cbt_capable:
                use_cbt = True
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message=f"Using Changed Block Tracking (CBT) for incremental backup"
                )
                db.add(log)
                await db.commit()
            else:
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message="Using QCOW2 backing file method for incremental backup"
                )
                db.add(log)
                await db.commit()

        # Get excluded_disks from backup metadata if provided
        excluded_disks = backup.backup_metadata.get('excluded_disks', []) if backup.backup_metadata else []

        # Get SSH password for disk operations if KVM host uses password authentication
        ssh_password = None
        if kvm_host.auth_type and kvm_host.auth_type.lower() == "password" and kvm_host.password_encrypted:
            from backend.core.encryption import decrypt_password
            from backend.core.config import settings
            ssh_password = decrypt_password(kvm_host.password_encrypted, settings.SECRET_KEY)

        # Initialize progress tracking
        progress_tracker = create_tracker(job.id)
        try:
            # Get VM disk info to initialize progress tracker
            vm_info = await kvm_service.get_vm_info(kvm_host.uri, vm.uuid)
            if vm_info.get('disks'):
                progress_tracker.initialize_disks(vm_info['disks'])
                progress_tracker.set_phase("disk_transfer")
                log = JobLog(
                    job_id=job.id,
                    level="DEBUG",
                    message=f"Progress tracking initialized for {len(vm_info['disks'])} disk(s)"
                )
                db.add(log)
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to initialize progress tracker: {e}")

        # Create progress callback for KVM service
        def on_disk_progress(disk_target: str, bytes_transferred: int, bytes_total: int):
            """Update progress tracker when disk bytes are transferred."""
            progress_tracker.update_disk(disk_target, bytes_transferred, bytes_total)

        # Attempt backup with checkpoint API, RBD-native, or CBT if requested, with fallback (Issue #15)
        backup_result = None
        cbt_fallback = False
        rbd_fallback = False
        new_checkpoint_name = None

        # Get parent RBD snapshots from parent backup's metadata (for RBD-native incremental)
        parent_rbd_snapshots = None
        if use_rbd_native and backup.parent_backup_id:
            parent_backup = await db.get(Backup, backup.parent_backup_id)
            if parent_backup and parent_backup.backup_metadata:
                parent_rbd_snapshots = parent_backup.backup_metadata.get("rbd_snapshots")

        try:
            if use_rbd_native:
                # Use RBD-native incremental backup (export-diff)
                backup_result = await kvm_service.create_rbd_incremental_backup(
                    uri=kvm_host.uri,
                    vm_uuid=vm.uuid,
                    backup_dir=backup_dir,
                    parent_snapshots=parent_rbd_snapshots,
                    ssh_password=ssh_password,
                    progress_callback=on_disk_progress
                )

                # Store RBD snapshot names in backup metadata for next incremental
                if backup_result.get("snapshots"):
                    if not backup.backup_metadata:
                        backup.backup_metadata = {}
                    backup.backup_metadata["rbd_snapshots"] = backup_result["snapshots"]
                    backup.backup_metadata["rbd_incremental"] = backup_result.get("incremental", False)
                    backup.backup_metadata["rbd_parent_snapshots"] = parent_rbd_snapshots or {}
                    # Flag the JSON field as modified so SQLAlchemy detects the change
                    flag_modified(backup, "backup_metadata")

            elif use_checkpoint_api:
                # Use the new checkpoint-based incremental backup
                import uuid as uuid_module
                new_checkpoint_name = f"backup-{vm.name}-{uuid_module.uuid4().hex[:8]}"

                backup_result = await kvm_service.create_incremental_backup(
                    uri=kvm_host.uri,
                    vm_uuid=vm.uuid,
                    backup_dir=backup_dir,
                    parent_checkpoint=parent_checkpoint,
                    new_checkpoint_name=new_checkpoint_name,
                    ssh_password=ssh_password
                )
            else:
                # Use traditional backup method
                # TODO: Pass excluded_disks to create_backup() once disk exclusion is implemented in KVMBackupService
                # For now, excluded_disks are stored in metadata but not enforced during backup
                backup_result = await kvm_service.create_backup(
                    uri=kvm_host.uri,
                    vm_uuid=vm.uuid,
                    backup_dir=backup_dir,
                    incremental=is_incremental,
                    use_cbt=use_cbt,
                    ssh_password=ssh_password,
                    progress_callback=on_disk_progress
                    # excluded_disks=excluded_disks  # TODO: Add this parameter to create_backup()
                )
        except Exception as e:
            if use_rbd_native:
                # RBD-native backup failed, fall back to full backup
                logger.warning(f"RBD-native incremental backup failed: {e}. Falling back to full backup.")
                log = JobLog(
                    job_id=job.id,
                    level="WARNING",
                    message=f"RBD-native incremental backup failed ({str(e)}), falling back to full backup"
                )
                db.add(log)
                await db.commit()

                rbd_fallback = True
                # Clear RBD snapshot tracking on fallback
                if backup.backup_metadata:
                    backup.backup_metadata.pop("rbd_snapshots", None)

                # Retry with full backup using traditional qemu-img method
                backup_result = await kvm_service.create_backup(
                    uri=kvm_host.uri,
                    vm_uuid=vm.uuid,
                    backup_dir=backup_dir,
                    incremental=False,
                    use_cbt=False,
                    ssh_password=ssh_password,
                    progress_callback=on_disk_progress
                )
                # Update backup mode to FULL since we fell back
                backup.backup_mode = BackupMode.FULL

            elif use_checkpoint_api or use_cbt:
                # Checkpoint/CBT backup failed, fall back to full backup
                logger.warning(f"Incremental backup failed: {e}. Falling back to full backup.")
                log = JobLog(
                    job_id=job.id,
                    level="WARNING",
                    message=f"Incremental backup failed ({str(e)}), falling back to full backup"
                )
                db.add(log)
                await db.commit()

                cbt_fallback = True
                new_checkpoint_name = None  # Don't create checkpoint on fallback
                # Retry with full backup
                backup_result = await kvm_service.create_backup(
                    uri=kvm_host.uri,
                    vm_uuid=vm.uuid,
                    backup_dir=backup_dir,
                    incremental=False,
                    use_cbt=False,
                    ssh_password=ssh_password,
                    progress_callback=on_disk_progress
                )
                # Update backup mode to FULL since we fell back
                backup.backup_mode = BackupMode.FULL
            else:
                # Not an incremental backup, re-raise error
                raise

        # Persist any pending verbose logs from KVM service
        if pending_logs:
            for log_entry in pending_logs:
                log = JobLog(
                    job_id=job.id,
                    level=log_entry["level"],
                    message=log_entry["message"],
                    details=log_entry.get("details"),
                    timestamp=log_entry.get("timestamp", datetime.utcnow())
                )
                db.add(log)
            await db.commit()
            logger.info(f"Persisted {len(pending_logs)} verbose log entries from KVM service")

        # Update backup with CBT metadata (Issue #15)
        if use_cbt and not cbt_fallback and 'cbt_metadata' in backup_result:
            cbt_meta = backup_result['cbt_metadata']
            backup.cbt_enabled = True
            backup.changed_blocks_count = cbt_meta.get('changed_blocks_count', 0)
            backup.bitmap_name = cbt_meta.get('bitmap_name') or cbt_meta.get('checkpoint_name')
            backup.block_size = cbt_meta.get('block_size')

            # Update schedule with checkpoint info for next incremental backup
            if schedule and new_checkpoint_name and not cbt_fallback:
                schedule.checkpoint_name = new_checkpoint_name
                # If this is a full backup (first in chain), update last_full_backup_id
                if not is_incremental or backup.backup_mode == BackupMode.FULL:
                    schedule.last_full_backup_id = backup.id
                # Cache incremental capability
                schedule.incremental_capable = True
                schedule.capability_checked_at = datetime.utcnow()
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message=f"Updated schedule with checkpoint: {new_checkpoint_name}"
                )
                db.add(log)
        else:
            backup.cbt_enabled = False

            # If this is a full backup without checkpoint (fallback or traditional),
            # reset the schedule's chain tracking
            if schedule and not is_incremental:
                schedule.last_full_backup_id = backup.id
                schedule.checkpoint_name = None  # Clear checkpoint for fresh chain

        # Update backup with application consistency metadata (Issue #14)
        backup.application_consistent = backup_result.get('application_consistent', False)
        backup.fsfreeze_status = backup_result.get('fsfreeze_status')
        backup.script_execution_log = backup_result.get('script_execution_log')

        if backup.application_consistent:
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Application-consistent backup created (filesystem frozen during snapshot)"
            )
            db.add(log)
        else:
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Crash-consistent backup created (fsfreeze status: {backup.fsfreeze_status or 'not attempted'})"
            )
            db.add(log)

        await db.commit()

        # Log
        log = JobLog(
            job_id=job.id,
            level="INFO",
            message=f"VM backup created. Size: {backup_result['total_size']} bytes"
        )
        db.add(log)
        await db.commit()

        # Update progress phase to archiving
        progress_tracker.set_phase("archiving")

        # Get user's compression preference, default to global setting
        compression_algorithm = settings.BACKUP_COMPRESSION
        if backup.backup_metadata:
            user_compression = backup.backup_metadata.get("compression_algorithm")
            if user_compression is not None:
                # Handle "none" as no compression
                if user_compression == "none" or user_compression == "":
                    compression_algorithm = None
                    log = JobLog(
                        job_id=job.id,
                        level="INFO",
                        message="Compression disabled by user preference"
                    )
                    db.add(log)
                    await db.commit()
                else:
                    compression_algorithm = user_compression

        # Create archive with user's compression preference
        archive_ext = ".tar" if compression_algorithm is None else f".tar.{compression_algorithm}" if compression_algorithm != "gz" else ".tar.gz"
        archive_file = Path(temp_dir) / f"{backup_dir.name}{archive_ext}"
        archive_result = await kvm_service.create_backup_archive(
            backup_dir=backup_dir,
            output_file=archive_file,
            compression=compression_algorithm
        )

        # Get storage backend for encryption strategy (Issue #11)
        from backend.models.storage import StorageBackend as StorageBackendModel, EncryptionStrategy
        storage_backend_model = await db.get(StorageBackendModel, backup.storage_backend_id)

        if not storage_backend_model:
            raise Exception("Storage backend not found")

        # Determine encryption strategy and key
        file_to_upload = archive_file
        encrypted = False
        encryption_key_to_use = None
        encryption_key_id = None

        # Check user's explicit encryption preference (overrides all other settings)
        user_encryption_enabled = backup.backup_metadata.get("encryption_enabled") if backup.backup_metadata else None

        if user_encryption_enabled is False:
            # User explicitly disabled encryption - respect their choice
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Encryption disabled by user preference"
            )
            db.add(log)
            await db.commit()

        elif storage_backend_model.encryption_strategy == EncryptionStrategy.APP_LEVEL or user_encryption_enabled is True:
            # Use storage-backend-specific encryption key (Issue #11)
            # Also use this path if user explicitly enabled encryption
            from backend.services.key_management import KeyManagementService
            key_service = KeyManagementService(db)

            encryption_key_bytes = await key_service.get_storage_backend_key(
                storage_backend_model.id,
                create_if_missing=True
            )

            if encryption_key_bytes:
                encryption_key_to_use = encryption_key_bytes.decode('utf-8')
                encryption_key_id = storage_backend_model.encryption_key_id
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message=f"Using storage-backend-specific encryption key (key ID: {encryption_key_id})"
                )
                db.add(log)
                await db.commit()
            elif user_encryption_enabled is True and settings.BACKUP_ENCRYPTION_ENABLED and settings.ENCRYPTION_KEY:
                # User wants encryption but no storage-specific key - fall back to global
                encryption_key_to_use = settings.ENCRYPTION_KEY
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message="Using global encryption key (user requested encryption)"
                )
                db.add(log)
                await db.commit()

        elif storage_backend_model.encryption_strategy == EncryptionStrategy.GLOBAL:
            # Use global encryption key (backward compatibility)
            if settings.BACKUP_ENCRYPTION_ENABLED and settings.ENCRYPTION_KEY:
                encryption_key_to_use = settings.ENCRYPTION_KEY
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message="Using global encryption key"
                )
                db.add(log)
                await db.commit()

        elif storage_backend_model.encryption_strategy == EncryptionStrategy.STORAGE_NATIVE:
            # Cloud-native encryption (S3 SSE, etc.) - handled by storage backend
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Using storage-native encryption (no app-level encryption)"
            )
            db.add(log)
            await db.commit()

        else:  # DISABLED
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Encryption disabled for this storage backend"
            )
            db.add(log)
            await db.commit()

        # Encrypt backup if we have a key
        if encryption_key_to_use:
            # Update progress phase to encrypting
            progress_tracker.set_phase("encrypting")

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Encrypting backup before upload..."
            )
            db.add(log)
            await db.commit()

            from backend.core.encryption import encrypt_backup
            encrypted_file = Path(temp_dir) / f"{archive_file.name}.encrypted"
            encryption_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: encrypt_backup(
                    archive_file,
                    encrypted_file,
                    encryption_key_to_use,
                    use_chunked=True  # Use chunked for large files
                )
            )

            file_to_upload = encrypted_file
            encrypted = True

            # Store encryption key ID in backup record (Issue #11)
            if encryption_key_id:
                backup.encryption_key_id = encryption_key_id

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Backup encrypted. Size: {encryption_result['original_size']} -> {encryption_result['encrypted_size']} bytes"
            )
            db.add(log)
            await db.commit()

        # Upload to storage
        progress_tracker.set_phase("uploading")

        storage = create_storage_backend(
            storage_backend_model.type,
            storage_backend_model.config
        )

        storage_path = f"vms/{vm.name}/{file_to_upload.name}"

        # Check if backup should be immutable (Issue #13)
        # Schedule can configure automatic immutability via schedule_metadata
        immutable_config = {}
        if schedule and schedule.schedule_metadata:
            immutable_config = schedule.schedule_metadata.get('immutability', {})

        upload_metadata = {
            "backup_id": str(backup.id),
            "vm_name": vm.name,
            "encrypted": encrypted
        }

        # Upload with S3 Object Lock if immutability configured
        if immutable_config.get('enabled') and storage_backend_model.type == 's3':
            from backend.services.storage.s3 import S3Storage
            from backend.models.backup import RetentionMode

            retention_mode = immutable_config.get('retention_mode', 'GOVERNANCE')
            retention_days = immutable_config.get('retention_days', 30)
            legal_hold = immutable_config.get('legal_hold', False)

            upload_result = await storage.upload_with_retention(
                source_path=file_to_upload,
                destination_path=storage_path,
                retention_mode=retention_mode,
                retention_days=retention_days,
                legal_hold=legal_hold,
                metadata=upload_metadata
            )

            # Mark backup as immutable in database
            from backend.services.immutability import ImmutabilityService
            immutability_service = ImmutabilityService(db)
            await immutability_service.make_backup_immutable(
                backup,
                retention_days=retention_days,
                retention_mode=RetentionMode(retention_mode),
                reason=immutable_config.get('reason', 'Scheduled immutable backup')
            )

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Immutable backup uploaded to storage with {retention_mode} retention: {storage_path}"
            )
            db.add(log)
        else:
            # Standard upload
            upload_result = await storage.upload(
                source_path=file_to_upload,
                destination_path=storage_path,
                metadata=upload_metadata
            )

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Backup uploaded to storage: {storage_path}"
            )
            db.add(log)

        await db.commit()

        # Clean up old RBD snapshots after successful backup (Phase 4)
        # We keep only the latest snapshot; delete the parent's snapshot
        if use_rbd_native and not rbd_fallback and parent_rbd_snapshots:
            from backend.services.storage.rbd import RBDBackupService
            rbd_service = RBDBackupService()

            # Extract SSH host from URI
            ssh_host = None
            ssh_match = re.search(r'qemu\+ssh://([^/]+)/', kvm_host.uri)
            if ssh_match:
                ssh_host = ssh_match.group(1)
            else:
                tcp_match = re.search(r'tcp://([^:/]+)', kvm_host.uri)
                if tcp_match:
                    ssh_host = f"root@{tcp_match.group(1)}"

            if ssh_host:
                for disk_target, old_snap in parent_rbd_snapshots.items():
                    # Find the disk info from backup result to get pool/image
                    disk_info = next(
                        (d for d in backup_result.get("disks", []) if d.get("target") == disk_target),
                        None
                    )
                    if disk_info and disk_info.get("rbd_pool") and disk_info.get("rbd_image"):
                        try:
                            deleted = await rbd_service.delete_snapshot(
                                disk_info["rbd_pool"],
                                disk_info["rbd_image"],
                                old_snap,
                                ssh_host,
                                ssh_password
                            )
                            if deleted:
                                log = JobLog(
                                    job_id=job.id,
                                    level="INFO",
                                    message=f"Deleted old RBD snapshot: {disk_info['rbd_pool']}/{disk_info['rbd_image']}@{old_snap}"
                                )
                                db.add(log)
                        except Exception as e:
                            # Log but don't fail the backup for snapshot cleanup errors
                            logger.warning(f"Failed to delete old RBD snapshot {old_snap}: {e}")
                            log = JobLog(
                                job_id=job.id,
                                level="WARNING",
                                message=f"Failed to clean up old RBD snapshot {old_snap}: {str(e)}"
                            )
                            db.add(log)

                await db.commit()

        # Clean up progress tracker
        remove_tracker(job.id)

        return {
            **archive_result,
            "storage_path": storage_path,
            "checksum": upload_result.get("checksum"),
            # Include storage encryption metadata (Issue #12)
            "storage_encryption_type": upload_result.get("storage_encryption_type"),
            "storage_encryption_key_id": upload_result.get("storage_encryption_key_id")
        }


async def _backup_container(db, schedule, backup, job):
    """Execute container backup."""
    from backend.models.infrastructure import Container, PodmanHost

    # Get container and host (use backup.source_id for both scheduled and one-time backups)
    container = await db.get(Container, backup.source_id)
    if not container:
        raise Exception(f"Container with ID {backup.source_id} not found")

    podman_host = await db.get(PodmanHost, container.podman_host_id)
    if not podman_host:
        raise Exception(f"Podman host not found for container {container.name}")

    # Log
    log = JobLog(
        job_id=job.id,
        level="INFO",
        message=f"Connecting to Podman host: {podman_host.name}"
    )
    db.add(log)
    await db.commit()

    # Create temp directory for backup
    with tempfile.TemporaryDirectory() as temp_dir:
        backup_dir = Path(temp_dir) / f"container_{container.name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Execute backup
        podman_service = PodmanBackupService()
        backup_result = await podman_service.create_backup(
            uri=podman_host.uri,
            container_id=container.container_id,
            backup_dir=backup_dir
        )

        # Log
        log = JobLog(
            job_id=job.id,
            level="INFO",
            message=f"Container backup created. Size: {backup_result['total_size']} bytes"
        )
        db.add(log)
        await db.commit()

        # Get user's compression preference, default to global setting
        compression_algorithm = settings.BACKUP_COMPRESSION
        if backup.backup_metadata:
            user_compression = backup.backup_metadata.get("compression_algorithm")
            if user_compression is not None:
                # Handle "none" as no compression
                if user_compression == "none" or user_compression == "":
                    compression_algorithm = None
                    log = JobLog(
                        job_id=job.id,
                        level="INFO",
                        message="Compression disabled by user preference"
                    )
                    db.add(log)
                    await db.commit()
                else:
                    compression_algorithm = user_compression

        # Create archive with user's compression preference
        archive_ext = ".tar" if compression_algorithm is None else f".tar.{compression_algorithm}" if compression_algorithm != "gz" else ".tar.gz"
        archive_file = Path(temp_dir) / f"{backup_dir.name}{archive_ext}"
        archive_result = await podman_service.create_backup_archive(
            backup_dir=backup_dir,
            output_file=archive_file,
            compression=compression_algorithm
        )

        # Get storage backend for encryption strategy
        from backend.models.storage import StorageBackend as StorageBackendModel, EncryptionStrategy
        storage_backend_model = await db.get(StorageBackendModel, backup.storage_backend_id)

        if not storage_backend_model:
            raise Exception("Storage backend not found")

        # Determine encryption strategy and key
        file_to_upload = archive_file
        encrypted = False
        encryption_key_to_use = None
        encryption_key_id = None

        # Check user's explicit encryption preference (overrides all other settings)
        user_encryption_enabled = backup.backup_metadata.get("encryption_enabled") if backup.backup_metadata else None

        if user_encryption_enabled is False:
            # User explicitly disabled encryption - respect their choice
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Encryption disabled by user preference"
            )
            db.add(log)
            await db.commit()

        elif storage_backend_model.encryption_strategy == EncryptionStrategy.APP_LEVEL or user_encryption_enabled is True:
            # Use storage-backend-specific encryption key
            from backend.services.key_management import KeyManagementService
            key_service = KeyManagementService(db)

            encryption_key_bytes = await key_service.get_storage_backend_key(
                storage_backend_model.id,
                create_if_missing=True
            )

            if encryption_key_bytes:
                encryption_key_to_use = encryption_key_bytes.decode('utf-8')
                encryption_key_id = storage_backend_model.encryption_key_id
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message=f"Using storage-backend-specific encryption key (key ID: {encryption_key_id})"
                )
                db.add(log)
                await db.commit()
            elif user_encryption_enabled is True and settings.BACKUP_ENCRYPTION_ENABLED and settings.ENCRYPTION_KEY:
                # User wants encryption but no storage-specific key - fall back to global
                encryption_key_to_use = settings.ENCRYPTION_KEY
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message="Using global encryption key (user requested encryption)"
                )
                db.add(log)
                await db.commit()

        elif storage_backend_model.encryption_strategy == EncryptionStrategy.GLOBAL:
            # Use global encryption key (backward compatibility)
            if settings.BACKUP_ENCRYPTION_ENABLED and settings.ENCRYPTION_KEY:
                encryption_key_to_use = settings.ENCRYPTION_KEY
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message="Using global encryption key"
                )
                db.add(log)
                await db.commit()

        elif storage_backend_model.encryption_strategy == EncryptionStrategy.STORAGE_NATIVE:
            # Cloud-native encryption (S3 SSE, etc.) - handled by storage backend
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Using storage-native encryption (no app-level encryption)"
            )
            db.add(log)
            await db.commit()

        else:  # DISABLED
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Encryption disabled for this storage backend"
            )
            db.add(log)
            await db.commit()

        # Encrypt backup if we have a key
        if encryption_key_to_use:
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Encrypting backup before upload..."
            )
            db.add(log)
            await db.commit()

            from backend.core.encryption import encrypt_backup
            encrypted_file = Path(temp_dir) / f"{archive_file.name}.encrypted"
            encryption_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: encrypt_backup(
                    archive_file,
                    encrypted_file,
                    encryption_key_to_use,
                    use_chunked=True  # Use chunked for large files
                )
            )

            file_to_upload = encrypted_file
            encrypted = True

            # Store encryption key ID in backup record
            if encryption_key_id:
                backup.encryption_key_id = encryption_key_id

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Backup encrypted. Size: {encryption_result['original_size']} -> {encryption_result['encrypted_size']} bytes"
            )
            db.add(log)
            await db.commit()

        # Upload to storage
        storage = create_storage_backend(
            storage_backend_model.type,
            storage_backend_model.config
        )

        storage_path = f"containers/{container.name}/{file_to_upload.name}"

        # Check if backup should be immutable (Issue #13)
        immutable_config = {}
        if schedule and schedule.schedule_metadata:
            immutable_config = schedule.schedule_metadata.get('immutability', {})

        upload_metadata = {
            "backup_id": str(backup.id),
            "container_name": container.name,
            "encrypted": encrypted
        }

        # Upload with S3 Object Lock if immutability configured
        if immutable_config.get('enabled') and storage_backend_model.type == 's3':
            from backend.services.storage.s3 import S3Storage
            from backend.models.backup import RetentionMode

            retention_mode = immutable_config.get('retention_mode', 'GOVERNANCE')
            retention_days = immutable_config.get('retention_days', 30)
            legal_hold = immutable_config.get('legal_hold', False)

            upload_result = await storage.upload_with_retention(
                source_path=file_to_upload,
                destination_path=storage_path,
                retention_mode=retention_mode,
                retention_days=retention_days,
                legal_hold=legal_hold,
                metadata=upload_metadata
            )

            # Mark backup as immutable in database
            from backend.services.immutability import ImmutabilityService
            immutability_service = ImmutabilityService(db)
            await immutability_service.make_backup_immutable(
                backup,
                retention_days=retention_days,
                retention_mode=RetentionMode(retention_mode),
                reason=immutable_config.get('reason', 'Scheduled immutable backup')
            )

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Immutable backup uploaded to storage with {retention_mode} retention: {storage_path}"
            )
        else:
            # Standard upload
            upload_result = await storage.upload(
                source_path=file_to_upload,
                destination_path=storage_path,
                metadata=upload_metadata
            )

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Backup uploaded to storage: {storage_path}"
            )
        db.add(log)
        await db.commit()

        return {
            **archive_result,
            "storage_path": storage_path,
            "checksum": upload_result.get("checksum"),
            # Include storage encryption metadata (Issue #12)
            "storage_encryption_type": upload_result.get("storage_encryption_type"),
            "storage_encryption_key_id": upload_result.get("storage_encryption_key_id")
        }


@celery_app.task(name="backend.worker.execute_restore")
def execute_restore(backup_id: int, target_host_id: Optional[int] = None, new_name: Optional[str] = None, overwrite: bool = False, storage_type: str = "auto", storage_config: Optional[dict] = None):
    """
    Execute a restore job.

    Args:
        backup_id: ID of the backup to restore
        target_host_id: ID of the target host (None = original host)
        new_name: New name for the restored VM/container (None = original name)
        overwrite: Whether to overwrite existing VM/container
        storage_type: Storage type: "auto" (detect from backup), "file", or "rbd"
        storage_config: Optional storage-specific configuration override
    """
    # Create a new event loop for this task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(_execute_restore_async(backup_id, target_host_id, new_name, overwrite, storage_type, storage_config))
    finally:
        loop.close()


async def _execute_restore_async(backup_id: int, target_host_id: Optional[int], new_name: Optional[str], overwrite: bool, storage_type: str = "auto", storage_config: Optional[dict] = None):
    """Async implementation of restore execution."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    # Create a new async engine for this event loop
    engine = create_async_engine(
        str(settings.DATABASE_URL),
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with SessionLocal() as db:
        job = None
        try:
            # Get backup
            backup = await db.get(Backup, backup_id)
            if not backup:
                raise Exception("Backup not found")

            if backup.status != BackupStatus.COMPLETED:
                raise Exception(f"Cannot restore backup with status: {backup.status}")

            # Find existing PENDING job created by API endpoint
            stmt = select(Job).where(
                Job.celery_task_id == celery_app.current_task.request.id
            )
            result = await db.execute(stmt)
            job = result.scalar_one_or_none()

            if not job:
                # If no job exists (shouldn't happen), create one
                job = Job(
                    type=JobType.RESTORE,
                    status=JobStatus.RUNNING,
                    backup_id=backup_id,
                    started_at=datetime.utcnow(),
                    celery_task_id=celery_app.current_task.request.id,
                    job_metadata={
                        "target_host_id": target_host_id,
                        "new_name": new_name,
                        "overwrite": overwrite
                    }
                )
                db.add(job)
            else:
                # Update existing job to RUNNING
                job.status = JobStatus.RUNNING
                job.started_at = datetime.utcnow()

            await db.commit()

            # Set logging context for this restore job
            with LoggingContext(job_id=job.id, backup_id=backup_id):
                # Log start
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message=f"Starting restore of {backup.source_type} {backup.source_name}"
                )
                db.add(log)
                await db.commit()

                # Execute restore based on source type
                if backup.source_type == SourceType.VM:
                    result = await _restore_vm(db, backup, job, target_host_id, new_name, overwrite, storage_type, storage_config)
                elif backup.source_type == SourceType.CONTAINER:
                    raise Exception("Container restore not yet implemented")
                else:
                    raise Exception(f"Unknown source type: {backup.source_type}")

                # Update job
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()

                # Log completion
                log = JobLog(
                    job_id=job.id,
                    level="INFO",
                    message=f"Restore completed successfully. Restored as: {result.get('vm_name', result.get('container_name', 'unknown'))}"
                )
                db.add(log)

                await db.commit()

                return {
                    "success": True,
                    "backup_id": backup_id,
                    "result": result
                }

        except Exception as e:
            # Set logging context for error handling
            with LoggingContext(job_id=job.id if job else None, backup_id=backup_id):
                # Update job
                if job:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)
                    job.completed_at = datetime.utcnow()

                    # Log error
                    log = JobLog(
                        job_id=job.id,
                        level="ERROR",
                        message=f"Restore failed: {str(e)}"
                    )
                    db.add(log)

                await db.commit()

                return {
                    "success": False,
                    "error": str(e)
                }
        finally:
            # Dispose engine to clean up connections
            await engine.dispose()


async def _restore_vm(db, backup, job, target_host_id, new_name, overwrite, storage_type="auto", storage_config=None):
    """Execute VM restore."""
    from backend.models.infrastructure import VM, KVMHost
    from backend.models.storage import StorageBackend as StorageBackendModel

    # Get original VM to determine original host if target not specified
    if target_host_id:
        target_host = await db.get(KVMHost, target_host_id)
        if not target_host:
            raise Exception(f"Target KVM host with ID {target_host_id} not found")
    else:
        # Restore to original host
        original_vm = await db.get(VM, backup.source_id)
        if not original_vm:
            raise Exception(f"Original VM with ID {backup.source_id} not found")
        target_host = await db.get(KVMHost, original_vm.kvm_host_id)
        if not target_host:
            raise Exception(f"Original KVM host not found for VM {backup.source_name}")

    # Log
    log = JobLog(
        job_id=job.id,
        level="INFO",
        message=f"Target KVM host: {target_host.name}"
    )
    db.add(log)
    await db.commit()

    # Get storage backend
    storage_backend_model = await db.get(StorageBackendModel, backup.storage_backend_id)
    if not storage_backend_model:
        raise Exception("Storage backend not found")

    storage = create_storage_backend(
        storage_backend_model.type,
        storage_backend_model.config
    )

    # Create temp directory for restore
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Download backup from storage
        log = JobLog(
            job_id=job.id,
            level="INFO",
            message=f"Downloading backup from storage: {backup.storage_path}"
        )
        db.add(log)
        await db.commit()

        downloaded_file = temp_path / Path(backup.storage_path).name
        await storage.download(
            source_path=backup.storage_path,
            destination_path=downloaded_file
        )

        # Decrypt if needed
        file_to_extract = downloaded_file
        if backup.storage_path.endswith('.encrypted'):
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message="Decrypting backup..."
            )
            db.add(log)
            await db.commit()

            from backend.core.encryption import decrypt_backup
            decrypted_file = temp_path / downloaded_file.name.replace('.encrypted', '')
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: decrypt_backup(
                    downloaded_file,
                    decrypted_file,
                    settings.ENCRYPTION_KEY,
                    use_chunked=True
                )
            )
            file_to_extract = decrypted_file

        # Extract archive
        log = JobLog(
            job_id=job.id,
            level="INFO",
            message="Extracting backup archive..."
        )
        db.add(log)
        await db.commit()

        extract_dir = temp_path / "extracted"
        extract_dir.mkdir()

        def _extract():
            import tarfile
            with tarfile.open(file_to_extract, 'r:gz') as tar:
                tar.extractall(extract_dir)

        await asyncio.get_event_loop().run_in_executor(None, _extract)

        # Find the backup directory (should be the only subdirectory)
        backup_dirs = [d for d in extract_dir.iterdir() if d.is_dir()]
        if not backup_dirs:
            raise Exception("No backup directory found in archive")

        backup_dir = backup_dirs[0]

        # Restore VM
        log = JobLog(
            job_id=job.id,
            level="INFO",
            message=f"Restoring VM to host {target_host.name}..."
        )
        db.add(log)
        await db.commit()

        kvm_service = KVMBackupService()
        restore_result = await kvm_service.restore_vm(
            uri=target_host.uri,
            backup_dir=backup_dir,
            new_name=new_name,
            overwrite=overwrite,
            storage_type=storage_type,
            storage_config=storage_config,
            host_config=target_host.config or {}
        )

        # If this is a new VM (not overwriting), create a new VM record
        if new_name and not overwrite:
            new_vm = VM(
                name=restore_result["vm_name"],
                uuid=restore_result["vm_uuid"],
                state="shutoff",
                vcpus=0,  # Will be updated on next discovery
                memory=0,
                kvm_host_id=target_host.id
            )
            db.add(new_vm)
            await db.commit()

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Created new VM record: {new_vm.name}"
            )
            db.add(log)
            await db.commit()

        return restore_result


@celery_app.task(name="backend.worker.check_scheduled_backups")
def check_scheduled_backups():
    """Check for scheduled backups that need to run."""
    import asyncio
    return asyncio.run(_check_scheduled_backups_async())


async def _check_scheduled_backups_async():
    """Async implementation of schedule checking."""
    async with AsyncSessionLocal() as db:
        # Get enabled schedules
        stmt = select(BackupSchedule).where(BackupSchedule.enabled == True)
        result = await db.execute(stmt)
        schedules = result.scalars().all()

        scheduled_count = 0
        now = datetime.utcnow()

        for schedule in schedules:
            # Check if backup is due
            if schedule.next_run and schedule.next_run <= now:
                # Create backup record
                backup = Backup(
                    schedule_id=schedule.id,
                    source_type=schedule.source_type,
                    source_id=schedule.source_id,
                    source_name="",  # Will be filled in by the task
                    backup_type=schedule.schedule_type,
                    status=BackupStatus.PENDING,
                    storage_backend_id=schedule.storage_backend_id
                )
                db.add(backup)
                await db.commit()
                await db.refresh(backup)

                # Schedule the backup task
                execute_backup.delay(schedule.id, backup.id)

                # Update schedule next_run using croniter
                from croniter import croniter
                cron = croniter(schedule.cron_expression, now)
                schedule.next_run = cron.get_next(datetime)
                schedule.last_run = now

                scheduled_count += 1

        await db.commit()

        return {"scheduled_count": scheduled_count}


@celery_app.task(name="backend.worker.apply_retention_policies")
def apply_retention_policies():
    """Apply retention policies to all schedules."""
    import asyncio
    return asyncio.run(_apply_retention_policies_async())


async def _apply_retention_policies_async():
    """Async implementation of retention policy application."""
    async with AsyncSessionLocal() as db:
        # Get all enabled schedules
        stmt = select(BackupSchedule).where(BackupSchedule.enabled == True)
        result = await db.execute(stmt)
        schedules = result.scalars().all()

        policy = RetentionPolicy()
        total_marked = 0

        for schedule in schedules:
            result = await policy.apply_retention(
                db=db,
                schedule_id=schedule.id,
                config=schedule.retention_config or {}
            )
            total_marked += result["deleted_count"]

        return {"schedules_processed": len(schedules), "backups_marked_for_deletion": total_marked}


@celery_app.task(name="backend.worker.cleanup_expired_backups")
def cleanup_expired_backups():
    """Delete backups that have expired."""
    import asyncio
    return asyncio.run(_cleanup_expired_backups_async())


async def _cleanup_expired_backups_async():
    """Async implementation of backup cleanup."""
    async with AsyncSessionLocal() as db:
        policy = RetentionPolicy()
        expired_backups = await policy.get_expired_backups(db, grace_period_hours=24)

        deleted_count = 0

        for backup in expired_backups:
            try:
                # Delete from storage
                from backend.models.storage import StorageBackend as StorageBackendModel
                storage_backend_model = await db.get(StorageBackendModel, backup.storage_backend_id)

                if storage_backend_model and backup.storage_path:
                    storage = create_storage_backend(
                        storage_backend_model.type,
                        storage_backend_model.config
                    )
                    await storage.delete(backup.storage_path)

                # Delete from database
                await db.delete(backup)
                deleted_count += 1

            except Exception as e:
                print(f"Error deleting backup {backup.id}: {e}")

        await db.commit()

        return {"deleted_count": deleted_count}


@celery_app.task(name="backend.worker.update_storage_usage")
def update_storage_usage():
    """Update storage usage statistics for all backends."""
    import asyncio
    return asyncio.run(_update_storage_usage_async())


async def _update_storage_usage_async():
    """Async implementation of storage usage update."""
    async with AsyncSessionLocal() as db:
        from backend.models.storage import StorageBackend as StorageBackendModel

        stmt = select(StorageBackendModel).where(StorageBackendModel.enabled == True)
        result = await db.execute(stmt)
        backends = result.scalars().all()

        alerts_sent = 0

        for backend_model in backends:
            try:
                storage = create_storage_backend(
                    backend_model.type,
                    backend_model.config
                )

                usage = await storage.get_usage()

                # Get usage values
                used_bytes = usage.get("used", 0)
                auto_capacity = usage.get("capacity", 0)

                # Determine capacity: use auto-detected if available, otherwise use quota_gb
                if auto_capacity > 0:
                    capacity_bytes = auto_capacity
                elif backend_model.quota_gb:
                    capacity_bytes = backend_model.quota_gb * (1024 ** 3)
                else:
                    capacity_bytes = 0

                # Update database fields (stored in GB)
                backend_model.used = used_bytes // (1024 ** 3)
                backend_model.capacity = capacity_bytes // (1024 ** 3) if capacity_bytes > 0 else None
                backend_model.last_check = datetime.utcnow().isoformat()

                # Check if threshold exceeded and send notification
                if capacity_bytes > 0:
                    used_percent = (used_bytes / capacity_bytes) * 100

                    if used_percent >= backend_model.threshold:
                        logger.warning(
                            f"Storage backend '{backend_model.name}' exceeded threshold: "
                            f"{used_percent:.1f}% used (threshold: {backend_model.threshold}%)"
                        )

                        # Send alert notification
                        try:
                            from backend.services.email import StorageAlertEmailService
                            alert_service = StorageAlertEmailService()
                            await alert_service.send_storage_threshold_alert(
                                backend_id=backend_model.id,
                                backend_name=backend_model.name,
                                backend_type=backend_model.type.value,
                                used_gb=used_bytes / (1024 ** 3),
                                capacity_gb=capacity_bytes / (1024 ** 3),
                                used_percent=used_percent,
                                threshold=backend_model.threshold
                            )
                            alerts_sent += 1
                        except Exception as alert_error:
                            logger.error(f"Failed to send storage alert for {backend_model.name}: {alert_error}")

            except Exception as e:
                logger.error(f"Error updating storage usage for {backend_model.name}: {e}")

        await db.commit()

        return {"backends_updated": len(backends), "alerts_sent": alerts_sent}


@celery_app.task(name="backend.worker.cleanup_logs")
def cleanup_logs():
    """Clean up old logs based on retention policies."""
    import asyncio
    return asyncio.run(_cleanup_logs_async())


async def _cleanup_logs_async():
    """Async implementation of log cleanup."""
    from backend.services.log_cleanup import run_log_cleanup

    try:
        stats = await run_log_cleanup()
        return stats
    except Exception as e:
        print(f"Error during log cleanup: {e}")
        return {"error": str(e)}


@celery_app.task(name="backend.worker.backup_database")
def backup_database():
    """
    Backup PostgreSQL database to configured storage backends.

    This critical task creates a complete backup of the PostgreSQL database
    including all tables, data, and encryption key metadata. The backup is
    compressed, optionally encrypted, and uploaded to all configured storage backends.
    """
    import asyncio
    return asyncio.run(_backup_database_async())


async def _backup_database_async():
    """Async implementation of database backup."""
    import subprocess
    import os
    from urllib.parse import urlparse
    from backend.core.encryption import encrypt_backup

    logger.info("Starting database backup task")

    async with AsyncSessionLocal() as db:
        try:
            # Parse database URL to get connection details
            db_url = str(settings.DATABASE_URL)
            parsed = urlparse(db_url)

            # Extract connection info
            db_host = parsed.hostname or "postgres"
            db_port = parsed.port or 5432
            db_user = parsed.username or "labbackup"
            db_name = parsed.path.lstrip('/') or "lab_backup"
            db_password = parsed.password

            # Create temporary directory for backup
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"database-backup-{timestamp}.sql.gz"

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                backup_file = temp_path / backup_filename

                logger.info(f"Creating database backup: {backup_filename}")

                # Set password environment variable for pg_dump
                env = os.environ.copy()
                if db_password:
                    env['PGPASSWORD'] = db_password

                # Execute pg_dump with compression
                # Using custom format (-Fc) for flexibility and compression
                dump_cmd = [
                    "pg_dump",
                    "-h", db_host,
                    "-p", str(db_port),
                    "-U", db_user,
                    "-d", db_name,
                    "-Fc",  # Custom format (compressed)
                    "-f", str(backup_file)
                ]

                result = subprocess.run(
                    dump_cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=1800  # 30 minute timeout
                )

                if result.returncode != 0:
                    error_msg = result.stderr or "Unknown error during pg_dump"
                    logger.error(f"Database backup failed: {error_msg}")
                    return {"success": False, "error": error_msg}

                backup_size = backup_file.stat().st_size
                logger.info(f"Database backup created: {backup_size} bytes")

                # Encrypt backup if encryption is enabled
                file_to_upload = backup_file
                encrypted = False

                if settings.BACKUP_ENCRYPTION_ENABLED and settings.ENCRYPTION_KEY:
                    logger.info("Encrypting database backup...")
                    encrypted_file = temp_path / f"{backup_filename}.encrypted"

                    encryption_result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: encrypt_backup(
                            backup_file,
                            encrypted_file,
                            settings.ENCRYPTION_KEY,
                            use_chunked=False  # Database backups typically < 1GB
                        )
                    )

                    file_to_upload = encrypted_file
                    encrypted = True
                    logger.info(f"Database backup encrypted: {encryption_result['encrypted_size']} bytes")

                # Get all enabled storage backends
                from backend.models.storage import StorageBackend as StorageBackendModel

                stmt = select(StorageBackendModel).where(StorageBackendModel.enabled == True)
                result = await db.execute(stmt)
                backends = result.scalars().all()

                if not backends:
                    logger.warning("No enabled storage backends found - database backup not uploaded")
                    return {
                        "success": True,
                        "warning": "No storage backends available",
                        "size": backup_size
                    }

                # Upload to all storage backends
                upload_results = []

                for backend_model in backends:
                    try:
                        logger.info(f"Uploading database backup to storage backend: {backend_model.name}")

                        storage = create_storage_backend(
                            backend_model.type,
                            backend_model.config
                        )

                        # Use dedicated path for database backups
                        storage_path = f"database-backups/{file_to_upload.name}"

                        upload_result = await storage.upload(
                            source_path=file_to_upload,
                            destination_path=storage_path,
                            metadata={
                                "backup_type": "database",
                                "timestamp": timestamp,
                                "encrypted": encrypted,
                                "database": db_name,
                                "compression": "pg_dump_custom"
                            }
                        )

                        upload_results.append({
                            "backend": backend_model.name,
                            "success": True,
                            "path": storage_path,
                            "size": upload_result.get("size", 0)
                        })

                        logger.info(f"Database backup uploaded to {backend_model.name}: {storage_path}")

                    except Exception as e:
                        logger.error(f"Failed to upload database backup to {backend_model.name}: {e}")
                        upload_results.append({
                            "backend": backend_model.name,
                            "success": False,
                            "error": str(e)
                        })

                # Return summary
                successful_uploads = sum(1 for r in upload_results if r.get("success"))

                return {
                    "success": True,
                    "timestamp": timestamp,
                    "backup_file": backup_filename,
                    "size": backup_size,
                    "encrypted": encrypted,
                    "storage_backends": len(backends),
                    "successful_uploads": successful_uploads,
                    "upload_results": upload_results
                }

        except subprocess.TimeoutExpired:
            logger.error("Database backup timed out after 30 minutes")
            return {"success": False, "error": "Backup timeout"}
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return {"success": False, "error": str(e)}


@celery_app.task(name="backend.worker.verify_backup")
def verify_backup(backup_id: int):
    """
    Verify a backup by restoring it to an isolated test pod.

    This task downloads the backup from storage, spins up an isolated
    PostgreSQL container, restores the backup, verifies the restoration,
    and tears down the test environment automatically.

    Args:
        backup_id: ID of the backup to verify

    Returns:
        Dict with verification results
    """
    import asyncio
    return asyncio.run(_verify_backup_async(backup_id))


async def _verify_backup_async(backup_id: int):
    """Async implementation of backup verification."""
    from backend.models.storage import StorageBackend as StorageBackendModel

    logger.info(f"Starting backup verification for backup ID: {backup_id}")

    async with AsyncSessionLocal() as db:
        try:
            # Get backup record
            backup = await db.get(Backup, backup_id)
            if not backup:
                logger.error(f"Backup not found: {backup_id}")
                return {"success": False, "error": "Backup not found"}

            # Create verification job
            job = Job(
                type=JobType.VERIFICATION,
                status=JobStatus.RUNNING,
                backup_id=backup_id,
                started_at=datetime.utcnow(),
                job_metadata={
                    "backup_id": backup_id,
                    "source_name": backup.source_name,
                    "backup_type": backup.backup_type.value
                }
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            logger.info(f"Created verification job ID: {job.id}")

            # Get storage backend
            storage_backend_model = await db.get(StorageBackendModel, backup.storage_backend_id)
            if not storage_backend_model:
                error_msg = "Storage backend not found"
                logger.error(error_msg)

                job.status = JobStatus.FAILED
                job.completed_at = datetime.utcnow()
                job.error_message = error_msg
                await db.commit()

                return {"success": False, "error": error_msg}

            # Download backup from storage
            logger.info(f"Downloading backup from storage: {backup.storage_path}")

            storage = create_storage_backend(
                storage_backend_model.type,
                storage_backend_model.config
            )

            # Create temporary directory for download
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                backup_filename = Path(backup.storage_path).name
                download_path = temp_path / backup_filename

                await storage.download(
                    source_path=backup.storage_path,
                    destination_path=download_path
                )

                logger.info(f"Backup downloaded to: {download_path}")

                # Check if backup is encrypted
                encrypted = download_path.name.endswith('.encrypted')

                # Create recovery test service
                recovery_service = RecoveryTestService(job_id=job.id)

                # Verify backup
                logger.info("Starting test pod verification...")
                verification_result = await recovery_service.verify_backup(
                    backup_file=download_path,
                    encrypted=encrypted
                )

                # Update backup record with verification results
                backup.verified = verification_result['success']
                backup.verification_date = datetime.utcnow()
                backup.verification_status = 'passed' if verification_result['success'] else 'failed'
                backup.verification_error = verification_result.get('error')
                backup.verification_job_id = job.id
                backup.verified_table_count = verification_result.get('table_count')
                backup.verified_size_bytes = verification_result.get('size_bytes')
                backup.verification_duration_seconds = verification_result.get('duration_seconds')

                # Update job status
                job.status = JobStatus.COMPLETED if verification_result['success'] else JobStatus.FAILED
                job.completed_at = datetime.utcnow()
                job.error_message = verification_result.get('error')
                job.job_metadata.update({
                    "verification_result": verification_result
                })

                await db.commit()

                logger.info(f"Backup verification completed: {verification_result['success']}")

                # Send email notification
                try:
                    from backend.services.email import VerificationEmailService
                    email_service = VerificationEmailService()
                    await email_service.send_verification_report(
                        backup_id=backup_id,
                        backup_name=Path(backup.storage_path).name if backup.storage_path else f"backup-{backup_id}",
                        source_name=backup.source_name,
                        backup_date=backup.created_at,
                        verification_success=verification_result['success'],
                        table_count=verification_result.get('table_count'),
                        size_bytes=verification_result.get('size_bytes'),
                        duration_seconds=verification_result.get('duration_seconds'),
                        error_message=verification_result.get('error')
                    )
                    logger.info("Verification email report sent")
                except Exception as email_error:
                    logger.error(f"Failed to send verification email: {email_error}", exc_info=True)

                return {
                    "success": verification_result['success'],
                    "job_id": job.id,
                    "backup_id": backup_id,
                    **verification_result
                }

        except Exception as e:
            logger.error(f"Backup verification failed: {e}", exc_info=True)

            # Update job if it exists
            error_message = str(e)
            try:
                if 'job' in locals():
                    job.status = JobStatus.FAILED
                    job.completed_at = datetime.utcnow()
                    job.error_message = error_message
                    await db.commit()
            except:
                pass

            # Send failure email notification
            try:
                if 'backup' in locals():
                    from backend.services.email import VerificationEmailService
                    email_service = VerificationEmailService()
                    await email_service.send_verification_report(
                        backup_id=backup_id,
                        backup_name=Path(backup.storage_path).name if backup.storage_path else f"backup-{backup_id}",
                        source_name=backup.source_name if backup else "Unknown",
                        backup_date=backup.created_at if backup else datetime.utcnow(),
                        verification_success=False,
                        error_message=error_message
                    )
                    logger.info("Verification failure email sent")
            except Exception as email_error:
                logger.error(f"Failed to send failure email: {email_error}")

            return {"success": False, "error": error_message}


@celery_app.task(name="backend.worker.verify_recent_backups")
def verify_recent_backups():
    """
    Scheduled task to verify the most recent backup for each source.

    This task runs weekly (Sunday at 5 AM) and automatically verifies
    the most recent completed backup for each VM and container.

    Returns:
        Dict with summary of verification tasks queued
    """
    import asyncio
    return asyncio.run(_verify_recent_backups_async())


async def _verify_recent_backups_async():
    """Async implementation of recent backups verification."""
    logger.info("Starting weekly backup verification task")

    async with AsyncSessionLocal() as db:
        try:
            # Get the most recent completed backup for each unique source
            # Using a subquery to find the max ID for each (source_type, source_id) pair
            from sqlalchemy import func

            subq = (
                select(
                    Backup.source_type,
                    Backup.source_id,
                    func.max(Backup.id).label('max_id')
                )
                .where(Backup.status == BackupStatus.COMPLETED)
                .group_by(Backup.source_type, Backup.source_id)
                .subquery()
            )

            stmt = (
                select(Backup)
                .join(
                    subq,
                    and_(
                        Backup.source_type == subq.c.source_type,
                        Backup.source_id == subq.c.source_id,
                        Backup.id == subq.c.max_id
                    )
                )
                .order_by(Backup.source_name)
            )

            result = await db.execute(stmt)
            recent_backups = result.scalars().all()

            if not recent_backups:
                logger.info("No completed backups found for verification")
                return {
                    "success": True,
                    "message": "No backups to verify",
                    "queued_count": 0
                }

            logger.info(f"Found {len(recent_backups)} backups to verify")

            # Queue verification for each backup
            queued = []
            for backup in recent_backups:
                try:
                    # Skip if already verified recently (within last 7 days)
                    if backup.verified and backup.verification_date:
                        days_since_verification = (datetime.utcnow() - backup.verification_date).days
                        if days_since_verification < 7:
                            logger.info(f"Skipping backup {backup.id} ({backup.source_name}) - verified {days_since_verification} days ago")
                            continue

                    # Queue verification task
                    task = verify_backup.delay(backup.id)
                    queued.append({
                        "backup_id": backup.id,
                        "source_name": backup.source_name,
                        "task_id": task.id
                    })
                    logger.info(f"Queued verification for backup {backup.id} ({backup.source_name})")

                except Exception as e:
                    logger.error(f"Failed to queue verification for backup {backup.id}: {e}")

            logger.info(f"Successfully queued {len(queued)} backup verifications")

            return {
                "success": True,
                "message": f"Queued {len(queued)} backups for verification",
                "queued_count": len(queued),
                "queued_backups": queued
            }

        except Exception as e:
            logger.error(f"Weekly backup verification task failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


@celery_app.task(name="backend.worker.calculate_compliance")
def calculate_compliance():
    """
    Calculate compliance status for all VMs and containers.

    This task runs hourly and updates the compliance status for all
    VMs and containers based on their backup schedules and RPO/RTO policies.

    Implements HYCU-style compliance state machine:
    - GREY: No backup policy assigned
    - GREEN: Fully compliant (backups within RPO)
    - YELLOW: Warning state (backup aging, minor issues)
    - RED: Non-compliant (no backups, RPO exceeded)

    Related: Issue #8 - Build Compliance Tracking System

    Returns:
        Dict with compliance calculation statistics
    """
    import asyncio
    return asyncio.run(_calculate_compliance_async())


async def _calculate_compliance_async():
    """Async implementation of compliance calculation."""
    from backend.services.compliance import ComplianceService

    logger.info("Starting compliance calculation task")

    async with AsyncSessionLocal() as db:
        try:
            compliance_service = ComplianceService(db)

            # Calculate compliance for all VMs and containers
            stats = await compliance_service.calculate_all_compliance()

            logger.info(
                f"Compliance calculation completed - "
                f"VMs: {stats['vms_updated']}, "
                f"Containers: {stats['containers_updated']}, "
                f"Errors: {stats['errors']}"
            )

            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                **stats
            }

        except Exception as e:
            logger.error(f"Compliance calculation failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


@celery_app.task(name="backend.worker.send_daily_compliance_summary")
def send_daily_compliance_summary():
    """
    Send daily compliance summary email.

    This task runs daily at 7 AM and sends a compliance summary report
    to configured email recipients. The report includes:
    - Overall compliance statistics (GREY/GREEN/YELLOW/RED breakdown)
    - List of all non-compliant (RED) entities
    - Trending and health percentage

    Related: Issue #8 - Build Compliance Tracking System

    Returns:
        Dict with email sending status
    """
    import asyncio
    return asyncio.run(_send_daily_compliance_summary_async())


async def _send_daily_compliance_summary_async():
    """Async implementation of daily compliance summary email."""
    from backend.services.compliance import ComplianceService
    from backend.services.email import ComplianceEmailService

    logger.info("Starting daily compliance summary email task")

    async with AsyncSessionLocal() as db:
        try:
            compliance_service = ComplianceService(db)

            # Get dashboard data
            dashboard_data = await compliance_service.get_compliance_dashboard()

            # Get non-compliant entities
            non_compliant_entities = await compliance_service.get_non_compliant_entities()

            # Send email
            email_service = ComplianceEmailService()
            await email_service.send_daily_compliance_summary(
                dashboard_data=dashboard_data,
                non_compliant_entities=non_compliant_entities
            )

            logger.info("Daily compliance summary email sent successfully")

            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "total_vms": dashboard_data['vms']['total'],
                "total_containers": dashboard_data['containers']['total'],
                "red_vms": dashboard_data['vms']['red'],
                "red_containers": dashboard_data['containers']['red']
            }

        except Exception as e:
            logger.error(f"Failed to send daily compliance summary: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
