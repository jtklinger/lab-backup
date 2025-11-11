"""
Backup schedule API endpoints.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional
from croniter import croniter

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.backup import BackupSchedule, SourceType, ScheduleType
from backend.core.security import get_current_user, require_role
from backend.worker import execute_backup

router = APIRouter()


class ScheduleCreate(BaseModel):
    name: str
    source_type: SourceType
    source_id: int
    schedule_type: ScheduleType
    cron_expression: str
    retention_config: dict
    storage_backend_id: int


class ScheduleResponse(BaseModel):
    id: int
    name: str
    source_type: SourceType
    source_id: int
    schedule_type: ScheduleType
    cron_expression: str
    storage_backend_id: int
    enabled: bool
    last_run: Optional[datetime]
    next_run: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("", response_model=List[ScheduleResponse])
async def list_schedules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all backup schedules."""
    stmt = select(BackupSchedule)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    schedule_data: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Create a new backup schedule."""
    # Validate cron expression
    try:
        cron = croniter(schedule_data.cron_expression, datetime.utcnow())
        next_run = cron.get_next(datetime)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cron expression: {str(e)}"
        )

    schedule = BackupSchedule(
        name=schedule_data.name,
        source_type=schedule_data.source_type,
        source_id=schedule_data.source_id,
        schedule_type=schedule_data.schedule_type,
        cron_expression=schedule_data.cron_expression,
        retention_config=schedule_data.retention_config,
        storage_backend_id=schedule_data.storage_backend_id,
        enabled=True,
        next_run=next_run
    )

    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    return schedule


@router.post("/{schedule_id}/run")
async def run_schedule_now(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Trigger a backup schedule immediately."""
    schedule = await db.get(BackupSchedule, schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found"
        )

    # Create backup record
    from backend.models.backup import Backup, BackupStatus

    backup = Backup(
        schedule_id=schedule.id,
        source_type=schedule.source_type,
        source_id=schedule.source_id,
        source_name="",
        backup_type=schedule.schedule_type,
        status=BackupStatus.PENDING,
        storage_backend_id=schedule.storage_backend_id
    )

    db.add(backup)
    await db.commit()
    await db.refresh(backup)

    # Queue the backup task
    task = execute_backup.delay(schedule.id, backup.id)

    return {
        "message": "Backup scheduled",
        "schedule_id": schedule_id,
        "backup_id": backup.id,
        "task_id": task.id
    }


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Delete a backup schedule."""
    schedule = await db.get(BackupSchedule, schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found"
        )

    await db.delete(schedule)
    await db.commit()

    return None
