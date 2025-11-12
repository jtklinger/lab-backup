"""
Celery worker configuration and tasks.
"""
import tempfile
from pathlib import Path
from datetime import datetime
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
def execute_backup(schedule_id: int, backup_id: int):
    """
    Execute a backup job.

    Args:
        schedule_id: ID of the backup schedule
        backup_id: ID of the backup record
    """
    import asyncio
    return asyncio.run(_execute_backup_async(schedule_id, backup_id))


async def _execute_backup_async(schedule_id: int, backup_id: int):
    """Async implementation of backup execution."""
    async with AsyncSessionLocal() as db:
        try:
            # Get schedule and backup
            schedule = await db.get(BackupSchedule, schedule_id)
            backup = await db.get(Backup, backup_id)

            if not schedule or not backup:
                raise Exception("Schedule or backup not found")

            # Create job record
            job = Job(
                type=JobType.BACKUP,
                status=JobStatus.RUNNING,
                backup_id=backup_id,
                started_at=datetime.utcnow(),
                celery_task_id=celery_app.current_task.request.id,
                metadata={"schedule_id": schedule_id}
            )
            db.add(job)
            await db.commit()

            # Update backup status
            backup.status = BackupStatus.RUNNING
            backup.started_at = datetime.utcnow()
            await db.commit()

            # Log start
            log = JobLog(
                job_id=job.id,
                level="INFO",
                message=f"Starting backup of {backup.source_type} {backup.source_name}"
            )
            db.add(log)
            await db.commit()

            # Execute backup based on source type
            if schedule.source_type == SourceType.VM:
                result = await _backup_vm(db, schedule, backup, job)
            elif schedule.source_type == SourceType.CONTAINER:
                result = await _backup_container(db, schedule, backup, job)
            else:
                raise Exception(f"Unknown source type: {schedule.source_type}")

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


async def _backup_vm(db, schedule, backup, job):
    """Execute VM backup."""
    from backend.models.infrastructure import VM, KVMHost

    # Get VM and host
    vm = await db.get(VM, schedule.source_id)
    kvm_host = await db.get(KVMHost, vm.kvm_host_id)

    if not vm or not kvm_host:
        raise Exception("VM or KVM host not found")

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
        backup_result = await kvm_service.create_backup(
            uri=kvm_host.uri,
            vm_uuid=vm.uuid,
            backup_dir=backup_dir
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
        storage_backend_model = await db.get(StorageBackendModel, schedule.storage_backend_id)

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

    # Get container and host
    container = await db.get(Container, schedule.source_id)
    podman_host = await db.get(PodmanHost, container.podman_host_id)

    if not container or not podman_host:
        raise Exception("Container or Podman host not found")

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
        storage_backend_model = await db.get(StorageBackendModel, schedule.storage_backend_id)

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
