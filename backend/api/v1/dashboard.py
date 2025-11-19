"""
Dashboard API endpoints.

Provides statistics and overview data for the main dashboard.
Related: Issue #16 - React Frontend
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.models.base import get_db
from backend.models.backup import Backup, Job, BackupSchedule, BackupStatus, JobStatus
from backend.models.infrastructure import VM, Container
from backend.core.security import get_current_user
from backend.models.user import User

router = APIRouter()


class DashboardStats(BaseModel):
    """Dashboard statistics model."""
    total_backups: int
    successful_backups: int
    failed_backups: int
    total_size_bytes: int
    active_jobs: int
    total_vms: int
    total_containers: int
    active_schedules: int


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get dashboard statistics.

    Returns counts and metrics for backups, VMs, containers, jobs, and schedules.
    """
    # Count total backups
    stmt = select(func.count(Backup.id))
    result = await db.execute(stmt)
    total_backups = result.scalar_one() or 0

    # Count successful backups
    stmt = select(func.count(Backup.id)).where(Backup.status == BackupStatus.COMPLETED)
    result = await db.execute(stmt)
    successful_backups = result.scalar_one() or 0

    # Count failed backups
    stmt = select(func.count(Backup.id)).where(Backup.status == BackupStatus.FAILED)
    result = await db.execute(stmt)
    failed_backups = result.scalar_one() or 0

    # Sum total backup size
    stmt = select(func.coalesce(func.sum(Backup.size_bytes), 0))
    result = await db.execute(stmt)
    total_size_bytes = result.scalar_one() or 0

    # Count active jobs (PENDING or RUNNING)
    stmt = select(func.count(Job.id)).where(
        Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
    )
    result = await db.execute(stmt)
    active_jobs = result.scalar_one() or 0

    # Count total VMs
    stmt = select(func.count(VM.id))
    result = await db.execute(stmt)
    total_vms = result.scalar_one() or 0

    # Count total containers
    stmt = select(func.count(Container.id))
    result = await db.execute(stmt)
    total_containers = result.scalar_one() or 0

    # Count active schedules
    stmt = select(func.count(BackupSchedule.id)).where(BackupSchedule.is_active == True)
    result = await db.execute(stmt)
    active_schedules = result.scalar_one() or 0

    return DashboardStats(
        total_backups=total_backups,
        successful_backups=successful_backups,
        failed_backups=failed_backups,
        total_size_bytes=total_size_bytes,
        active_jobs=active_jobs,
        total_vms=total_vms,
        total_containers=total_containers,
        active_schedules=active_schedules
    )
