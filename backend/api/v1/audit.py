"""
Audit Log API endpoints.

Related: Issue #9 - Enhance audit logging system
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional
import csv
import io
import json

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.audit import AuditLog
from backend.core.security import get_current_user, require_role
from backend.services.audit import AuditLogService

router = APIRouter()


class AuditLogResponse(BaseModel):
    """Audit log response model."""
    id: int
    created_at: datetime
    user_id: Optional[int]
    username: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    resource_name: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    request_method: Optional[str]
    request_path: Optional[str]
    response_status: Optional[int]
    response_message: Optional[str]
    duration_ms: Optional[int]
    severity: str
    tags: Optional[List[str]]

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Paginated audit log list response."""
    logs: List[AuditLogResponse]
    total: int
    limit: int
    offset: int


class AuditStatsResponse(BaseModel):
    """Audit log statistics response."""
    total_logs: int
    by_severity: dict
    top_actions: dict
    top_users: dict
    start_date: Optional[str]
    end_date: Optional[str]


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    severity: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    ip_address: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Query audit logs with filters."""
    audit_service = AuditLogService(db)
    logs, total = await audit_service.query_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        severity=severity,
        start_date=start_date,
        end_date=end_date,
        ip_address=ip_address,
        limit=limit,
        offset=offset
    )

    return {
        "logs": logs,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/recent")
async def get_recent_activity(
    user_id: Optional[int] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get recent activity logs."""
    # Non-admins can only view their own activity
    if current_user.role != UserRole.ADMIN:
        user_id = current_user.id

    audit_service = AuditLogService(db)
    logs = await audit_service.get_recent_activity(
        user_id=user_id,
        limit=limit
    )

    return {"logs": [AuditLogResponse.from_orm(log) for log in logs]}


@router.get("/statistics", response_model=AuditStatsResponse)
async def get_audit_statistics(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Get audit log statistics."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    audit_service = AuditLogService(db)
    stats = await audit_service.get_statistics(
        start_date=start_date,
        end_date=end_date
    )

    return stats


@router.get("/export/csv")
async def export_audit_logs_csv(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    severity: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 10000,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Export audit logs to CSV for compliance reports."""
    audit_service = AuditLogService(db)
    logs, _ = await audit_service.query_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        severity=severity,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=0
    )

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        'Timestamp', 'User', 'Action', 'Resource Type', 'Resource ID',
        'Resource Name', 'IP Address', 'Method', 'Path', 'Status',
        'Duration (ms)', 'Severity', 'Message'
    ])

    # Write rows
    for log in logs:
        writer.writerow([
            log.created_at.isoformat(),
            log.username or 'SYSTEM',
            log.action,
            log.resource_type or '',
            log.resource_id or '',
            log.resource_name or '',
            log.ip_address or '',
            log.request_method or '',
            log.request_path or '',
            log.response_status or '',
            log.duration_ms or '',
            log.severity,
            log.response_message or ''
        ])

    # Return as downloadable CSV
    output.seek(0)
    filename = f"audit_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/json")
async def export_audit_logs_json(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    severity: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 10000,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Export audit logs to JSON for SIEM ingestion."""
    audit_service = AuditLogService(db)
    logs, total = await audit_service.query_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        severity=severity,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=0
    )

    # Convert to JSON-serializable format
    logs_data = []
    for log in logs:
        logs_data.append({
            "timestamp": log.created_at.isoformat(),
            "user_id": log.user_id,
            "username": log.username,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "resource_name": log.resource_name,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "request_method": log.request_method,
            "request_path": log.request_path,
            "request_data": log.request_data,
            "response_status": log.response_status,
            "response_message": log.response_message,
            "duration_ms": log.duration_ms,
            "severity": log.severity,
            "tags": log.tags,
            "metadata": log.audit_metadata
        })

    result = {
        "total": total,
        "count": len(logs_data),
        "exported_at": datetime.utcnow().isoformat(),
        "logs": logs_data
    }

    filename = f"audit_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

    return StreamingResponse(
        iter([json.dumps(result, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Get specific audit log by ID."""
    log = await db.get(AuditLog, log_id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found"
        )

    return log
