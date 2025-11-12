"""
Backup API endpoints.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.backup import Backup, BackupStatus, ScheduleType
from backend.core.security import get_current_user, require_role

router = APIRouter()


class BackupResponse(BaseModel):
    id: int
    schedule_id: int
    source_name: str
    backup_type: ScheduleType
    status: BackupStatus
    size: Optional[int]
    compressed_size: Optional[int]
    storage_path: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


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
