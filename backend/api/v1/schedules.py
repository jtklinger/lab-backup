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
    # Incremental backup configuration (Issue #15)
    backup_mode_policy: str = "auto"  # auto, full_only, incremental_preferred
    max_chain_length: int = 14
    full_backup_day: Optional[int] = None  # 0-6 for weekly, 1-31 for monthly


class ScheduleUpdate(BaseModel):
    """Request model for updating schedule configuration."""
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    retention_config: Optional[dict] = None
    enabled: Optional[bool] = None
    # Incremental backup configuration (Issue #15)
    backup_mode_policy: Optional[str] = None
    max_chain_length: Optional[int] = None
    full_backup_day: Optional[int] = None


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
    # Incremental backup configuration (Issue #15)
    backup_mode_policy: str = "auto"
    max_chain_length: int = 14
    full_backup_day: Optional[int] = None
    last_full_backup_id: Optional[int] = None
    checkpoint_name: Optional[str] = None
    incremental_capable: Optional[bool] = None
    capability_checked_at: Optional[datetime] = None

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
        next_run=next_run,
        # Incremental backup configuration (Issue #15)
        backup_mode_policy=schedule_data.backup_mode_policy,
        max_chain_length=schedule_data.max_chain_length,
        full_backup_day=schedule_data.full_backup_day
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


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a backup schedule by ID."""
    schedule = await db.get(BackupSchedule, schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found"
        )
    return schedule


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: int,
    update_data: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """
    Update a backup schedule.

    Allows updating:
    - name
    - cron_expression
    - retention_config
    - enabled
    - backup_mode_policy (auto, full_only, incremental_preferred)
    - max_chain_length
    - full_backup_day

    Related: Issue #15 - Implement Changed Block Tracking (CBT)
    """
    schedule = await db.get(BackupSchedule, schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found"
        )

    # Update fields that were provided
    if update_data.name is not None:
        schedule.name = update_data.name

    if update_data.cron_expression is not None:
        # Validate cron expression
        try:
            cron = croniter(update_data.cron_expression, datetime.utcnow())
            schedule.cron_expression = update_data.cron_expression
            schedule.next_run = cron.get_next(datetime)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid cron expression: {str(e)}"
            )

    if update_data.retention_config is not None:
        schedule.retention_config = update_data.retention_config

    if update_data.enabled is not None:
        schedule.enabled = update_data.enabled

    # Incremental backup configuration (Issue #15)
    if update_data.backup_mode_policy is not None:
        if update_data.backup_mode_policy not in ["auto", "full_only", "incremental_preferred"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="backup_mode_policy must be one of: auto, full_only, incremental_preferred"
            )
        schedule.backup_mode_policy = update_data.backup_mode_policy

    if update_data.max_chain_length is not None:
        if update_data.max_chain_length < 1 or update_data.max_chain_length > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="max_chain_length must be between 1 and 100"
            )
        schedule.max_chain_length = update_data.max_chain_length

    if update_data.full_backup_day is not None:
        # Validate based on schedule type
        if schedule.schedule_type == ScheduleType.WEEKLY:
            if update_data.full_backup_day < 0 or update_data.full_backup_day > 6:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="full_backup_day must be 0-6 for weekly schedules"
                )
        elif schedule.schedule_type == ScheduleType.MONTHLY:
            if update_data.full_backup_day < 1 or update_data.full_backup_day > 31:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="full_backup_day must be 1-31 for monthly schedules"
                )
        schedule.full_backup_day = update_data.full_backup_day

    await db.commit()
    await db.refresh(schedule)

    return schedule


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


@router.post("/{schedule_id}/check-incremental-support")
async def check_incremental_support(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """
    Check if the VM associated with this schedule supports incremental backups.

    This queries the hypervisor to verify:
    - libvirt version (requires 6.0+)
    - QEMU version (requires 4.2+)
    - Disk types and their support for checkpoints
    - Recommended backup method

    The result is cached on the schedule for future reference.

    Related: Issue #15 - Implement Changed Block Tracking (CBT)
    """
    schedule = await db.get(BackupSchedule, schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found"
        )

    if schedule.source_type != SourceType.VM:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incremental backup support check only applicable for VMs"
        )

    # Get the VM and its KVM host
    from backend.models.infrastructure import VM, KVMHost
    vm = await db.get(VM, schedule.source_id)
    if not vm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated VM not found"
        )

    kvm_host = await db.get(KVMHost, vm.host_id)
    if not kvm_host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated KVM host not found"
        )

    # Check incremental support
    from backend.services.kvm.backup import KVMBackupService
    kvm_service = KVMBackupService()

    try:
        support = await kvm_service.check_incremental_support(
            uri=kvm_host.uri,
            vm_uuid=vm.uuid
        )

        # Update schedule with cached result
        schedule.incremental_capable = support["supported"]
        schedule.capability_checked_at = datetime.utcnow()
        await db.commit()

        return {
            "schedule_id": schedule_id,
            "vm_name": vm.name,
            **support
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check incremental support: {str(e)}"
        )
