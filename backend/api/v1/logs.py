"""
Logs API endpoints.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from backend.models.user import User
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
