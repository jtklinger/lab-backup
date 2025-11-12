"""
Job API endpoints.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.models.backup import Job, JobLog, JobStatus, JobType
from backend.core.security import get_current_user

router = APIRouter()


class JobResponse(BaseModel):
    id: int
    type: JobType
    status: JobStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class JobLogResponse(BaseModel):
    id: int
    timestamp: datetime
    level: str
    message: str

    class Config:
        from_attributes = True


@router.get("", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[JobStatus] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List jobs."""
    stmt = select(Job)

    if status:
        stmt = stmt.where(Job.status == status)

    stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get job details."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/logs", response_model=List[JobLogResponse])
async def get_job_logs(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get job logs."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    stmt = select(JobLog).where(JobLog.job_id == job_id).order_by(JobLog.timestamp)
    result = await db.execute(stmt)
    return result.scalars().all()
