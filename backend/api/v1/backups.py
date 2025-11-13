"""
Backup API endpoints.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import List, Optional

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.backup import Backup, BackupStatus, BackupMode, ScheduleType, SourceType
from backend.models.infrastructure import VM, Container
from backend.models.settings import SystemSetting
from backend.core.security import get_current_user, require_role

router = APIRouter()


class BackupResponse(BaseModel):
    id: int
    schedule_id: Optional[int]
    source_name: str
    source_type: SourceType
    backup_type: ScheduleType
    backup_mode: BackupMode
    parent_backup_id: Optional[int]
    status: BackupStatus
    size: Optional[int]
    compressed_size: Optional[int]
    storage_path: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


class TriggerBackupRequest(BaseModel):
    """Request model for triggering one-time backup."""
    source_type: SourceType = Field(..., description="Type of source: vm or container")
    source_id: int = Field(..., description="ID of the VM or Container to backup")
    backup_mode: BackupMode = Field(BackupMode.FULL, description="Backup mode: full or incremental")
    storage_backend_id: int = Field(..., description="ID of storage backend to use")
    encryption_enabled: bool = Field(False, description="Whether to encrypt the backup")
    retention_days: Optional[int] = Field(None, description="Retention period in days (defaults to system setting)")


async def find_parent_backup(
    source_type: SourceType,
    source_id: int,
    db: AsyncSession
) -> Optional[Backup]:
    """Find the most recent completed FULL backup for the given source."""
    stmt = select(Backup).where(
        and_(
            Backup.source_type == source_type,
            Backup.source_id == source_id,
            Backup.backup_mode == BackupMode.FULL,
            Backup.status == BackupStatus.COMPLETED
        )
    ).order_by(Backup.completed_at.desc()).limit(1)

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post("/trigger", response_model=BackupResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_backup(
    request: TriggerBackupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """
    Trigger a one-time backup of a VM or container.

    For INCREMENTAL backups, the system automatically finds the most recent FULL backup
    as the parent. If no parent backup exists, returns an error.
    """
    # Validate source exists
    if request.source_type == SourceType.VM:
        source = await db.get(VM, request.source_id)
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"VM with ID {request.source_id} not found"
            )
        source_name = source.name
    elif request.source_type == SourceType.CONTAINER:
        source = await db.get(Container, request.source_id)
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Container with ID {request.source_id} not found"
            )
        source_name = source.name
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source_type: {request.source_type}"
        )

    # For incremental backups, find parent backup
    parent_backup_id = None
    if request.backup_mode == BackupMode.INCREMENTAL:
        parent_backup = await find_parent_backup(request.source_type, request.source_id, db)
        if not parent_backup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No parent FULL backup found for {request.source_type} {source_name}. "
                       "Create a FULL backup first before running incremental backups."
            )
        parent_backup_id = parent_backup.id

    # Get retention period
    retention_days = request.retention_days
    if retention_days is None:
        # Load from system settings
        stmt = select(SystemSetting).where(SystemSetting.key == "default_one_time_retention_days")
        result = await db.execute(stmt)
        setting = result.scalar_one_or_none()
        retention_days = int(setting.value) if setting else 30

    # Calculate expiration date
    expires_at = datetime.utcnow() + timedelta(days=retention_days)

    # Create backup record
    backup = Backup(
        schedule_id=None,  # One-time backup has no schedule
        source_type=request.source_type,
        source_id=request.source_id,
        source_name=source_name,
        backup_type=ScheduleType.DAILY,  # One-time backups use "daily" type
        backup_mode=request.backup_mode,
        parent_backup_id=parent_backup_id,
        status=BackupStatus.PENDING,
        storage_backend_id=request.storage_backend_id,
        expires_at=expires_at,
        backup_metadata={
            "one_time": True,
            "encryption_enabled": request.encryption_enabled,
            "triggered_by": current_user.username,
            "triggered_at": datetime.utcnow().isoformat()
        }
    )

    db.add(backup)
    await db.commit()
    await db.refresh(backup)

    # Queue backup job via Celery
    from backend.worker import execute_backup
    task = execute_backup.delay(None, backup.id)  # schedule_id is None for one-time backups

    # Update backup with task ID
    from backend.models.backup import Job, JobType, JobStatus
    job = Job(
        type=JobType.BACKUP,
        status=JobStatus.PENDING,
        backup_id=backup.id,
        celery_task_id=task.id
    )
    db.add(job)
    await db.commit()
    await db.refresh(backup)

    return backup


@router.get("", response_model=List[BackupResponse])
async def list_backups(
    status: Optional[BackupStatus] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List backups with optional filtering."""
    stmt = select(Backup)

    if status:
        stmt = stmt.where(Backup.status == status)

    stmt = stmt.order_by(Backup.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{backup_id}", response_model=BackupResponse)
async def get_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get backup details."""
    backup = await db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )
    return backup


@router.delete("/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Delete a backup."""
    backup = await db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )

    # Delete from storage
    if backup.storage_path:
        from backend.services.storage import create_storage_backend
        from backend.models.storage import StorageBackend as StorageBackendModel

        storage_backend = await db.get(StorageBackendModel, backup.storage_backend_id)
        if storage_backend:
            storage = create_storage_backend(storage_backend.type, storage_backend.config)
            await storage.delete(backup.storage_path)

    # Delete from database
    await db.delete(backup)
    await db.commit()

    return None


@router.post("/{backup_id}/restore")
async def restore_backup(
    backup_id: int,
    target_host_id: Optional[int] = None,
    new_name: Optional[str] = None,
    overwrite: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Restore a backup (VM or container)."""
    backup = await db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )

    # TODO: Implement restore logic
    # This would involve:
    # 1. Download backup from storage
    # 2. Extract archive
    # 3. Restore VM/container using appropriate service
    # 4. Handle rename/overwrite options

    return {
        "message": "Restore functionality coming soon",
        "backup_id": backup_id
    }
