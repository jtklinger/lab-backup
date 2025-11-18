"""
Audit log API endpoints for querying and exporting audit trails.

Provides:
- Audit log filtering (user, action, resource_type, date range, severity)
- CSV/JSON export for compliance reporting
- Audit statistics dashboard
- SIEM-ready structured logs

Related: Issue #9 - Enhanced Audit Logging System
"""
from datetime import datetime, timedelta
from typing import Optional, List, Literal
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import csv
import io
import json

from backend.models.base import get_db
from backend.models.user import User, AuditLog, UserRole
from backend.core.security import get_current_user
from backend.core.config import settings
from backend.services.siem_integration import get_siem_integration, configure_siem_integration, SyslogConfig

router = APIRouter()


class AuditLogResponse(BaseModel):
    """Audit log entry response model."""
    id: int
    created_at: datetime
    user_id: Optional[int]
    username: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    details: Optional[dict]
    ip_address: Optional[str]
    user_agent: Optional[str]
    request_method: Optional[str]
    request_path: Optional[str]
    request_data: Optional[dict]
    response_status: Optional[int]
    duration_ms: Optional[float]
    severity: Optional[str]

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Paginated audit log list response."""
    total: int
    page: int
    page_size: int
    logs: List[AuditLogResponse]


class AuditStatsResponse(BaseModel):
    """Audit statistics response."""
    total_logs: int
    total_users: int
    recent_logins: int
    failed_logins: int
    api_requests_24h: int
    average_response_time_ms: float
    severity_breakdown: dict
    top_actions: List[dict]
    top_users: List[dict]


def require_admin(current_user: User = Depends(get_current_user)):
    """Dependency to require admin role for audit access."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access audit logs"
        )
    return current_user


@router.get("/logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Results per page"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action (e.g., AUTH_LOGIN_SUCCESS)"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    search: Optional[str] = Query(None, description="Search in action or details"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get paginated audit logs with filtering.

    Supports filtering by:
    - user_id: Specific user
    - action: Action type (e.g., AUTH_LOGIN_SUCCESS, API_POST)
    - resource_type: Resource type (e.g., BACKUP, USER, VM)
    - severity: Log severity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - start_date/end_date: Date range
    - search: Full-text search in action or details
    """
    # Build filter conditions
    conditions = []

    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)

    if action:
        conditions.append(AuditLog.action == action)

    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)

    if severity:
        conditions.append(AuditLog.severity == severity)

    if start_date:
        conditions.append(AuditLog.created_at >= start_date)

    if end_date:
        conditions.append(AuditLog.created_at <= end_date)

    if search:
        # Search in action or convert details to text for searching
        conditions.append(
            or_(
                AuditLog.action.ilike(f"%{search}%"),
                AuditLog.request_path.ilike(f"%{search}%") if AuditLog.request_path else False
            )
        )

    # Count total matching records
    count_stmt = select(func.count()).select_from(AuditLog)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # Get paginated results
    offset = (page - 1) * page_size
    stmt = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    if conditions:
        stmt = stmt.where(and_(*conditions))

    result = await db.execute(stmt)
    logs = result.scalars().all()

    # Enrich with username if user_id exists
    log_responses = []
    for log in logs:
        log_dict = {
            "id": log.id,
            "created_at": log.created_at,
            "user_id": log.user_id,
            "username": None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": log.details,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "request_method": log.request_method,
            "request_path": log.request_path,
            "request_data": log.request_data,
            "response_status": log.response_status,
            "duration_ms": log.duration_ms,
            "severity": log.severity
        }

        # Get username if user exists
        if log.user_id:
            user_stmt = select(User).where(User.id == log.user_id)
            user_result = await db.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            if user:
                log_dict["username"] = user.username

        log_responses.append(AuditLogResponse(**log_dict))

    return AuditLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        logs=log_responses
    )


@router.get("/logs/export")
async def export_audit_logs(
    format: str = Query("csv", regex="^(csv|json)$", description="Export format (csv or json)"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum records to export"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export audit logs to CSV or JSON format.

    Useful for compliance reporting and SIEM integration.
    Applies same filters as /logs endpoint.
    """
    # Build filter conditions (same as get_audit_logs)
    conditions = []

    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)

    if action:
        conditions.append(AuditLog.action == action)

    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)

    if severity:
        conditions.append(AuditLog.severity == severity)

    if start_date:
        conditions.append(AuditLog.created_at >= start_date)

    if end_date:
        conditions.append(AuditLog.created_at <= end_date)

    # Get logs
    stmt = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )

    if conditions:
        stmt = stmt.where(and_(*conditions))

    result = await db.execute(stmt)
    logs = result.scalars().all()

    # Generate filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if format == "csv":
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "id", "created_at", "user_id", "action", "resource_type", "resource_id",
            "ip_address", "user_agent", "request_method", "request_path",
            "response_status", "duration_ms", "severity", "details"
        ])

        # Write data
        for log in logs:
            writer.writerow([
                log.id,
                log.created_at.isoformat() if log.created_at else "",
                log.user_id or "",
                log.action,
                log.resource_type or "",
                log.resource_id or "",
                log.ip_address or "",
                log.user_agent or "",
                log.request_method or "",
                log.request_path or "",
                log.response_status or "",
                log.duration_ms or "",
                log.severity or "",
                json.dumps(log.details) if log.details else ""
            ])

        # Return CSV response
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit_logs_{timestamp}.csv"
            }
        )

    else:  # json format
        # Convert to JSON
        logs_data = []
        for log in logs:
            logs_data.append({
                "id": log.id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "user_id": log.user_id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "request_method": log.request_method,
                "request_path": log.request_path,
                "request_data": log.request_data,
                "response_status": log.response_status,
                "duration_ms": log.duration_ms,
                "severity": log.severity
            })

        json_str = json.dumps(logs_data, indent=2)

        return StreamingResponse(
            iter([json_str]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=audit_logs_{timestamp}.json"
            }
        )


@router.get("/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get audit log statistics for dashboard.

    Provides:
    - Total log count
    - Recent login activity
    - Failed login attempts
    - API request volume (24h)
    - Average response time
    - Severity breakdown
    - Top actions
    - Top users by activity
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Total logs in period
    total_stmt = select(func.count()).select_from(AuditLog).where(
        AuditLog.created_at >= cutoff_date
    )
    total_result = await db.execute(total_stmt)
    total_logs = total_result.scalar_one()

    # Total unique users
    users_stmt = select(func.count(func.distinct(AuditLog.user_id))).where(
        AuditLog.created_at >= cutoff_date,
        AuditLog.user_id.isnot(None)
    )
    users_result = await db.execute(users_stmt)
    total_users = users_result.scalar_one()

    # Recent successful logins
    logins_stmt = select(func.count()).select_from(AuditLog).where(
        AuditLog.created_at >= cutoff_date,
        AuditLog.action == "AUTH_LOGIN_SUCCESS"
    )
    logins_result = await db.execute(logins_stmt)
    recent_logins = logins_result.scalar_one()

    # Failed logins
    failed_stmt = select(func.count()).select_from(AuditLog).where(
        AuditLog.created_at >= cutoff_date,
        AuditLog.action == "AUTH_LOGIN_FAILURE"
    )
    failed_result = await db.execute(failed_stmt)
    failed_logins = failed_result.scalar_one()

    # API requests in last 24 hours
    api_24h_stmt = select(func.count()).select_from(AuditLog).where(
        AuditLog.created_at >= datetime.utcnow() - timedelta(hours=24),
        AuditLog.request_method.isnot(None)
    )
    api_24h_result = await db.execute(api_24h_stmt)
    api_requests_24h = api_24h_result.scalar_one()

    # Average response time
    avg_time_stmt = select(func.avg(AuditLog.duration_ms)).where(
        AuditLog.created_at >= cutoff_date,
        AuditLog.duration_ms.isnot(None)
    )
    avg_time_result = await db.execute(avg_time_stmt)
    avg_response_time = avg_time_result.scalar_one() or 0.0

    # Severity breakdown
    severity_stmt = select(
        AuditLog.severity,
        func.count().label('count')
    ).where(
        AuditLog.created_at >= cutoff_date
    ).group_by(AuditLog.severity)

    severity_result = await db.execute(severity_stmt)
    severity_breakdown = {
        row.severity or "UNKNOWN": row.count
        for row in severity_result
    }

    # Top 10 actions
    actions_stmt = select(
        AuditLog.action,
        func.count().label('count')
    ).where(
        AuditLog.created_at >= cutoff_date
    ).group_by(AuditLog.action).order_by(func.count().desc()).limit(10)

    actions_result = await db.execute(actions_stmt)
    top_actions = [
        {"action": row.action, "count": row.count}
        for row in actions_result
    ]

    # Top 10 users by activity
    users_stmt = select(
        AuditLog.user_id,
        func.count().label('count')
    ).where(
        AuditLog.created_at >= cutoff_date,
        AuditLog.user_id.isnot(None)
    ).group_by(AuditLog.user_id).order_by(func.count().desc()).limit(10)

    users_result = await db.execute(users_stmt)
    top_user_ids = [(row.user_id, row.count) for row in users_result]

    # Get usernames for top users
    top_users = []
    for user_id, count in top_user_ids:
        user_stmt = select(User).where(User.id == user_id)
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        top_users.append({
            "user_id": user_id,
            "username": user.username if user else f"[Deleted User {user_id}]",
            "count": count
        })

    return AuditStatsResponse(
        total_logs=total_logs,
        total_users=total_users,
        recent_logins=recent_logins,
        failed_logins=failed_logins,
        api_requests_24h=api_requests_24h,
        average_response_time_ms=round(avg_response_time, 2),
        severity_breakdown=severity_breakdown,
        top_actions=top_actions,
        top_users=top_users
    )


@router.get("/actions")
async def get_available_actions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get list of all unique actions in audit logs (for filter dropdowns)."""
    stmt = select(AuditLog.action).distinct().order_by(AuditLog.action)
    result = await db.execute(stmt)
    actions = [row[0] for row in result if row[0]]

    return {"actions": actions}


@router.get("/resource-types")
async def get_available_resource_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get list of all unique resource types in audit logs (for filter dropdowns)."""
    stmt = select(AuditLog.resource_type).distinct().order_by(AuditLog.resource_type)
    result = await db.execute(stmt)
    resource_types = [row[0] for row in result if row[0]]

    return {"resource_types": resource_types}


class SIEMConfigResponse(BaseModel):
    """SIEM configuration response model."""
    enabled: bool
    host: Optional[str]
    port: int
    protocol: str
    format: str
    facility: int


@router.get("/siem/config", response_model=SIEMConfigResponse)
async def get_siem_config(
    current_user: User = Depends(require_admin)
):
    """
    Get current SIEM/Syslog configuration.

    Only accessible to administrators.
    """
    return SIEMConfigResponse(
        enabled=settings.SIEM_ENABLED,
        host=settings.SIEM_HOST,
        port=settings.SIEM_PORT,
        protocol=settings.SIEM_PROTOCOL,
        format=settings.SIEM_FORMAT,
        facility=settings.SIEM_FACILITY
    )


class SIEMConfigUpdate(BaseModel):
    """SIEM configuration update model."""
    enabled: bool = Field(description="Enable SIEM export")
    host: str = Field(description="Syslog server hostname")
    port: int = Field(ge=1, le=65535, description="Syslog server port")
    protocol: Literal["udp", "tcp"] = Field(description="Transport protocol")
    format: Literal["rfc5424", "cef"] = Field(description="Log format")
    facility: int = Field(ge=0, le=23, description="Syslog facility")


@router.post("/siem/config")
async def update_siem_config(
    config: SIEMConfigUpdate,
    current_user: User = Depends(require_admin)
):
    """
    Update SIEM/Syslog configuration.

    Note: This updates runtime configuration only. To persist across restarts,
    update environment variables in .env file.

    Only accessible to administrators.
    """
    # Update runtime settings
    settings.SIEM_ENABLED = config.enabled
    settings.SIEM_HOST = config.host
    settings.SIEM_PORT = config.port
    settings.SIEM_PROTOCOL = config.protocol
    settings.SIEM_FORMAT = config.format
    settings.SIEM_FACILITY = config.facility

    # Reconfigure SIEM integration
    siem_config = SyslogConfig(
        enabled=config.enabled,
        host=config.host,
        port=config.port,
        protocol=config.protocol,
        format=config.format,
        facility=config.facility,
        app_name=settings.APP_NAME
    )
    configure_siem_integration(siem_config)

    return {
        "message": "SIEM configuration updated",
        "config": config,
        "note": "Configuration is runtime-only. Update .env file to persist across restarts."
    }


@router.post("/siem/test")
async def test_siem_connection(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Test SIEM connection by sending a test audit log.

    Only accessible to administrators.
    """
    siem = get_siem_integration()

    if not siem or not siem.config.enabled:
        raise HTTPException(
            status_code=400,
            detail="SIEM integration is not enabled. Configure SIEM first."
        )

    # Create a test audit log entry
    from backend.services.audit_logger import AuditLogger
    audit_logger = AuditLogger(db)

    try:
        test_log = await audit_logger.log_event(
            action="SIEM_TEST",
            user_id=current_user.id,
            resource_type="SYSTEM",
            details={"test": True, "message": "SIEM integration test"},
            severity="INFO"
        )

        # The audit logger automatically exports to SIEM
        # Check if it was successful (we can't really know from here, but we tried)
        return {
            "message": "Test audit log sent to SIEM",
            "siem_config": {
                "host": siem.config.host,
                "port": siem.config.port,
                "protocol": siem.config.protocol,
                "format": siem.config.format
            },
            "test_log_id": test_log.id,
            "note": "Check your SIEM system to verify receipt. No errors means UDP packet was sent (TCP would error on connection failure)."
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test log to SIEM: {str(e)}"
        )
