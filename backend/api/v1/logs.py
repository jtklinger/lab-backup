"""
Logs API endpoints.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, func, and_

from backend.models.user import User
from backend.models.base import get_db, AsyncSession
from backend.models.logs import ApplicationLog
from backend.core.security import get_current_user, require_role
from backend.core.logging_handler import get_log_handler

router = APIRouter()


class LogEntry(BaseModel):
    """Log entry model."""
    timestamp: str
    level: str
    logger: str
    message: str
    module: str
    funcName: str
    lineno: int
    pathname: str
    exception: Optional[str] = None


class LogsResponse(BaseModel):
    """Logs response model."""
    logs: List[LogEntry]
    total: int
    offset: int
    limit: int


class LogStats(BaseModel):
    """Log statistics model."""
    total: int
    max_records: int
    by_level: Dict[str, int]


@router.get("", response_model=LogsResponse)
async def get_logs(
    level: Optional[str] = Query(None, description="Filter by log level"),
    logger: Optional[str] = Query(None, description="Filter by logger name"),
    search: Optional[str] = Query(None, description="Search in log messages"),
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    current_user: User = Depends(get_current_user)
):
    """
    Get application logs with optional filtering.

    Requires authentication. Returns most recent logs first.
    """
    handler = get_log_handler()
    logs = handler.get_logs(
        level=level,
        logger=logger,
        search=search,
        limit=limit,
        offset=offset
    )

    return {
        "logs": logs,
        "total": len(logs),
        "offset": offset,
        "limit": limit
    }


@router.get("/stats", response_model=LogStats)
async def get_log_stats(
    current_user: User = Depends(get_current_user)
):
    """Get log statistics."""
    handler = get_log_handler()
    stats = handler.get_stats()
    return stats


@router.post("/clear", status_code=204)
async def clear_logs(
    current_user: User = Depends(require_role("admin"))
):
    """Clear all stored logs. Requires admin role."""
    handler = get_log_handler()
    handler.clear()
    return None


# ========== Application Logs (Database) ==========

class ApplicationLogEntry(BaseModel):
    """Application log entry from database."""
    id: int
    timestamp: datetime
    level: str
    logger: str
    message: str
    module: Optional[str] = None
    function: Optional[str] = None
    line_number: Optional[int] = None
    pathname: Optional[str] = None
    exception: Optional[str] = None
    job_id: Optional[int] = None
    backup_id: Optional[int] = None
    user_id: Optional[int] = None
    request_id: Optional[str] = None

    class Config:
        from_attributes = True


class ApplicationLogsResponse(BaseModel):
    """Application logs response model."""
    logs: List[ApplicationLogEntry]
    total: int
    offset: int
    limit: int


class ApplicationLogStats(BaseModel):
    """Application log statistics."""
    total: int
    by_level: Dict[str, int]


@router.get("/application", response_model=ApplicationLogsResponse)
async def get_application_logs(
    level: Optional[str] = Query(None, description="Filter by log level"),
    logger: Optional[str] = Query(None, description="Filter by logger name"),
    search: Optional[str] = Query(None, description="Search in log messages"),
    job_id: Optional[int] = Query(None, description="Filter by job ID"),
    backup_id: Optional[int] = Query(None, description="Filter by backup ID"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    request_id: Optional[str] = Query(None, description="Filter by request ID"),
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get application logs from database with optional filtering.

    Requires authentication. Returns most recent logs first.
    """
    # Build query
    query = select(ApplicationLog)

    # Apply filters
    filters = []
    if level:
        filters.append(ApplicationLog.level == level.upper())
    if logger:
        filters.append(ApplicationLog.logger.ilike(f"%{logger}%"))
    if search:
        filters.append(ApplicationLog.message.ilike(f"%{search}%"))
    if job_id is not None:
        filters.append(ApplicationLog.job_id == job_id)
    if backup_id is not None:
        filters.append(ApplicationLog.backup_id == backup_id)
    if user_id is not None:
        filters.append(ApplicationLog.user_id == user_id)
    if request_id:
        filters.append(ApplicationLog.request_id == request_id)

    if filters:
        query = query.where(and_(*filters))

    # Get total count
    count_query = select(func.count()).select_from(ApplicationLog)
    if filters:
        count_query = count_query.where(and_(*filters))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get logs (most recent first)
    query = query.order_by(ApplicationLog.timestamp.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "logs": logs,
        "total": total,
        "offset": offset,
        "limit": limit
    }


@router.get("/application/stats", response_model=ApplicationLogStats)
async def get_application_log_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get application log statistics from database."""
    # Get total count
    total_result = await db.execute(select(func.count()).select_from(ApplicationLog))
    total = total_result.scalar() or 0

    # Get counts by level
    by_level = {}
    for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        level_result = await db.execute(
            select(func.count())
            .select_from(ApplicationLog)
            .where(ApplicationLog.level == level)
        )
        by_level[level] = level_result.scalar() or 0

    return {
        "total": total,
        "by_level": by_level
    }


@router.delete("/application", status_code=204)
async def delete_application_logs(
    older_than_days: Optional[int] = Query(None, description="Delete logs older than N days"),
    level: Optional[str] = Query(None, description="Delete logs of specific level"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Delete application logs from database.

    Requires admin role. Can delete all logs or filter by age/level.
    """
    from datetime import timedelta, timezone

    query = select(ApplicationLog)
    filters = []

    if older_than_days is not None:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        filters.append(ApplicationLog.timestamp < cutoff_date)

    if level:
        filters.append(ApplicationLog.level == level.upper())

    if filters:
        query = query.where(and_(*filters))

    # Delete matching logs
    result = await db.execute(query)
    logs_to_delete = result.scalars().all()

    for log in logs_to_delete:
        await db.delete(log)

    await db.commit()
    return None
