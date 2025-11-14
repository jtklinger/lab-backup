"""
Celery worker configuration and tasks.
"""
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from backend.core.config import settings
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
    "apply-retention-policies": {
        "task": "backend.worker.apply_retention_policies",
        "schedule": crontab(hour="2", minute="0"),  # Daily at 2 AM
    },
    "cleanup-expired-backups": {
        "task": "backend.worker.cleanup_expired_backups",
        "schedule": crontab(hour="3", minute="0"),  # Daily at 3 AM
    },
    "update-storage-usage": {
        "task": "backend.worker.update_storage_usage",
        "schedule": crontab(hour="*/6", minute="0"),  # Every 6 hours
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

            # Create job record
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
            await db.commit()

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
            backup.completed_at = datetime.utcnow()
            backup.size = result.get("original_size", 0)
            backup.compressed_size = result.get("compressed_size", 0)
            backup.storage_path = result.get("storage_path")
            backup.checksum = result.get("checksum")

            # Update job
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()

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

        # Execute backup
        kvm_service = KVMBackupService()

        # Determine if incremental backup is requested
        from backend.models.backup import BackupMode
        is_incremental = hasattr(backup, 'backup_mode') and backup.backup_mode == BackupMode.INCREMENTAL

        backup_result = await kvm_service.create_backup(
            uri=kvm_host.uri,
            vm_uuid=vm.uuid,
            backup_dir=backup_dir,
            incremental=is_incremental
        )

        # Log
        log = JobLog(
            job_id=job.id,
            level="INFO",
            message=f"VM backup created. Size: {backup_result['total_size']} bytes"
        )
        db.add(log)
        await db.commit()

        # Create archive
        archive_file = Path(temp_dir) / f"{backup_dir.name}.tar.gz"
        archive_result = await kvm_service.create_backup_archive(
            backup_dir=backup_dir,
            output_file=archive_file,
            compression=settings.BACKUP_COMPRESSION
        )

        # Encrypt backup if enabled
        file_to_upload = archive_file
        encrypted = False
        if settings.BACKUP_ENCRYPTION_ENABLED and settings.ENCRYPTION_KEY:
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
                    settings.ENCRYPTION_KEY,
                    use_chunked=True  # Use chunked for large files
                )
            )

            file_to_upload = encrypted_file
            encrypted = True

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Backup encrypted. Size: {encryption_result['original_size']} -> {encryption_result['encrypted_size']} bytes"
            )
            db.add(log)
            await db.commit()

        # Upload to storage
        from backend.models.storage import StorageBackend as StorageBackendModel
        storage_backend_model = await db.get(StorageBackendModel, backup.storage_backend_id)

        if not storage_backend_model:
            raise Exception("Storage backend not found")

        storage = create_storage_backend(
            storage_backend_model.type,
            storage_backend_model.config
        )

        storage_path = f"vms/{vm.name}/{file_to_upload.name}"
        upload_result = await storage.upload(
            source_path=file_to_upload,
            destination_path=storage_path,
            metadata={
                "backup_id": str(backup.id),
                "vm_name": vm.name,
                "encrypted": encrypted
            }
        )

        # Log
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
            "checksum": upload_result.get("checksum")
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

        # Create archive
        archive_file = Path(temp_dir) / f"{backup_dir.name}.tar.gz"
        archive_result = await podman_service.create_backup_archive(
            backup_dir=backup_dir,
            output_file=archive_file,
            compression=settings.BACKUP_COMPRESSION
        )

        # Encrypt backup if enabled
        file_to_upload = archive_file
        encrypted = False
        if settings.BACKUP_ENCRYPTION_ENABLED and settings.ENCRYPTION_KEY:
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
                    settings.ENCRYPTION_KEY,
                    use_chunked=True  # Use chunked for large files
                )
            )

            file_to_upload = encrypted_file
            encrypted = True

            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Backup encrypted. Size: {encryption_result['original_size']} -> {encryption_result['encrypted_size']} bytes"
            )
            db.add(log)
            await db.commit()

        # Upload to storage
        from backend.models.storage import StorageBackend as StorageBackendModel
        storage_backend_model = await db.get(StorageBackendModel, backup.storage_backend_id)

        if not storage_backend_model:
            raise Exception("Storage backend not found")

        storage = create_storage_backend(
            storage_backend_model.type,
            storage_backend_model.config
        )

        storage_path = f"containers/{container.name}/{file_to_upload.name}"
        upload_result = await storage.upload(
            source_path=file_to_upload,
            destination_path=storage_path,
            metadata={
                "backup_id": str(backup.id),
                "container_name": container.name,
                "encrypted": encrypted
            }
        )

        # Log
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
            "checksum": upload_result.get("checksum")
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

            # Create job record
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
            await db.commit()

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

        for backend_model in backends:
            try:
                storage = create_storage_backend(
                    backend_model.type,
                    backend_model.config
                )

                usage = await storage.get_usage()

                backend_model.used = usage.get("used", 0) // (1024 ** 3)  # Convert to GB
                backend_model.capacity = usage.get("capacity", 0) // (1024 ** 3)
                backend_model.last_check = datetime.utcnow().isoformat()

            except Exception as e:
                print(f"Error updating storage usage for {backend_model.name}: {e}")

        await db.commit()

        return {"backends_updated": len(backends)}
