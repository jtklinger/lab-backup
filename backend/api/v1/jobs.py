"""
Job API endpoints.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.backup import Job, JobLog, JobStatus, JobType
from backend.core.security import get_current_user

router = APIRouter()


class JobResponse(BaseModel):
    id: int
    type: JobType
    status: JobStatus
    backup_id: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_job(cls, job: Job) -> "JobResponse":
        """Convert a Job ORM object to a JobResponse."""
        return cls(
            id=job.id,
            type=job.type,
            status=job.status,
            backup_id=job.backup_id,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error_message=job.error_message,
            metadata=job.job_metadata,
            created_at=job.created_at,
        )


class JobLogResponse(BaseModel):
    id: int
    timestamp: datetime
    level: str
    message: str
    details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class JobsListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    limit: int
    offset: int


@router.get("", response_model=JobsListResponse)
async def list_jobs(
    status: Optional[JobStatus] = None,
    job_type: Optional[JobType] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List jobs with filtering and pagination."""
    # Check role - operators and above only
    if current_user.role not in [UserRole.ADMIN, UserRole.OPERATOR]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Build base query
    conditions = []

    if status:
        conditions.append(Job.status == status)

    if job_type:
        conditions.append(Job.type == job_type)

    if start_date:
        conditions.append(Job.created_at >= start_date)

    if end_date:
        conditions.append(Job.created_at <= end_date)

    # Get total count
    count_stmt = select(func.count(Job.id))
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Get paginated results
    stmt = select(Job)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    jobs = result.scalars().all()

    # Convert ORM objects to response models
    job_responses = [JobResponse.from_orm_job(job) for job in jobs]
    return JobsListResponse(jobs=job_responses, total=total, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get job details."""
    # Check role - operators and above only
    if current_user.role not in [UserRole.ADMIN, UserRole.OPERATOR]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_orm_job(job)


@router.get("/{job_id}/logs", response_model=List[JobLogResponse])
async def get_job_logs(
    job_id: int,
    level: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get job logs with optional level filtering."""
    # Check role - operators and above only
    if current_user.role not in [UserRole.ADMIN, UserRole.OPERATOR]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    stmt = select(JobLog).where(JobLog.job_id == job_id)
    if level:
        stmt = stmt.where(JobLog.level == level.upper())
    stmt = stmt.order_by(JobLog.timestamp)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel a running or pending job."""
    # Check role - operators and above only
    if current_user.role not in [UserRole.ADMIN, UserRole.OPERATOR]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status {job.status}")

    # TODO: Actually cancel the Celery task if running
    # For now, just mark as cancelled
    job.status = JobStatus.CANCELLED
    job.completed_at = datetime.utcnow()

    # Add cancellation log
    cancel_log = JobLog(
        job_id=job_id,
        level="WARNING",
        message=f"Job cancelled by user {current_user.username}",
        details={"cancelled_by": current_user.username, "previous_status": job.status.value}
    )
    db.add(cancel_log)

    await db.commit()
    return {"message": "Job cancelled successfully"}
