"""
Audit Logging Service

Provides centralized audit logging for security and compliance tracking.

Related: Issue #9 - Enhance audit logging system
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.audit import AuditLog, AuditAction, AuditSeverity, ResourceType
from backend.models.user import User

logger = logging.getLogger(__name__)


class AuditLogService:
    """Service for creating and querying audit logs."""

    # Sensitive field names to sanitize from request data
    SENSITIVE_FIELDS = {
        'password', 'token', 'secret', 'key', 'api_key', 'access_key',
        'secret_key', 'private_key', 'encryption_key', 'kms_key',
        'auth_token', 'refresh_token', 'jwt', 'credentials'
    }

    def __init__(self, db: AsyncSession):
        """
        Initialize audit log service.

        Args:
            db: Async database session
        """
        self.db = db

    async def log(
        self,
        action: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        resource_name: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        response_status: Optional[int] = None,
        response_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        severity: str = AuditSeverity.INFO.value,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Create an audit log entry.

        Args:
            action: Action performed (use AuditAction enum values)
            user_id: ID of user who performed action
            username: Username snapshot
            resource_type: Type of resource affected
            resource_id: ID of resource
            resource_name: Name of resource
            ip_address: Client IP address
            user_agent: User agent string
            request_method: HTTP method
            request_path: API path
            request_data: Request payload (will be sanitized)
            response_status: HTTP status code
            response_message: Response message
            duration_ms: Request duration
            severity: Log severity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            tags: Searchable tags
            metadata: Additional context

        Returns:
            Created AuditLog instance
        """
        # Sanitize request data
        sanitized_request = self._sanitize_data(request_data) if request_data else None

        # Create audit log
        audit_log = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            request_data=sanitized_request,
            response_status=response_status,
            response_message=response_message,
            duration_ms=duration_ms,
            severity=severity,
            tags=tags,
            audit_metadata=metadata
        )

        self.db.add(audit_log)
        await self.db.commit()
        await self.db.refresh(audit_log)

        # Log to application logger for debugging
        logger.info(
            f"AUDIT: {action} by {username or 'SYSTEM'} "
            f"({resource_type}:{resource_id if resource_id else 'N/A'}) "
            f"[{severity}]"
        )

        return audit_log

    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove sensitive information from request data.

        Args:
            data: Request data dictionary

        Returns:
            Sanitized copy of data
        """
        if not isinstance(data, dict):
            return data

        sanitized = {}
        for key, value in data.items():
            # Check if key is sensitive
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts
                sanitized[key] = self._sanitize_data(value)
            elif isinstance(value, list):
                # Sanitize list items
                sanitized[key] = [
                    self._sanitize_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    async def log_authentication(
        self,
        username: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None
    ) -> AuditLog:
        """
        Log authentication attempt.

        Args:
            username: Username attempting authentication
            success: Whether authentication succeeded
            ip_address: Client IP
            user_agent: User agent
            failure_reason: Reason for failure (if applicable)

        Returns:
            Created AuditLog instance
        """
        action = AuditAction.LOGIN_SUCCESS.value if success else AuditAction.LOGIN_FAILURE.value
        severity = AuditSeverity.INFO.value if success else AuditSeverity.WARNING.value

        return await self.log(
            action=action,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            response_status=200 if success else 401,
            response_message="Login successful" if success else failure_reason,
            severity=severity,
            tags=["authentication", "security"]
        )

    async def log_resource_access(
        self,
        action: str,
        resource_type: str,
        resource_id: int,
        resource_name: str,
        user: User,
        ip_address: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        response_status: Optional[int] = None,
        response_message: Optional[str] = None
    ) -> AuditLog:
        """
        Log resource access or modification.

        Args:
            action: Action performed (CREATE, UPDATE, DELETE, etc.)
            resource_type: Type of resource
            resource_id: Resource ID
            resource_name: Resource name
            user: User performing action
            ip_address: Client IP
            request_data: Request payload
            response_status: HTTP status
            response_message: Response message

        Returns:
            Created AuditLog instance
        """
        return await self.log(
            action=action,
            user_id=user.id,
            username=user.username,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            ip_address=ip_address,
            request_data=request_data,
            response_status=response_status,
            response_message=response_message,
            tags=["resource", resource_type.lower()]
        )

    async def query_logs(
        self,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        severity: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        ip_address: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[AuditLog], int]:
        """
        Query audit logs with filters.

        Args:
            user_id: Filter by user ID
            action: Filter by action
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            severity: Filter by severity
            start_date: Filter by start date
            end_date: Filter by end date
            ip_address: Filter by IP address
            limit: Maximum results
            offset: Results offset

        Returns:
            Tuple of (logs list, total count)
        """
        # Build query
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)

        # Apply filters
        filters = []
        if user_id is not None:
            filters.append(AuditLog.user_id == user_id)
        if action:
            filters.append(AuditLog.action == action)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if resource_id is not None:
            filters.append(AuditLog.resource_id == resource_id)
        if severity:
            filters.append(AuditLog.severity == severity)
        if start_date:
            filters.append(AuditLog.created_at >= start_date)
        if end_date:
            filters.append(AuditLog.created_at <= end_date)
        if ip_address:
            filters.append(AuditLog.ip_address == ip_address)

        if filters:
            stmt = stmt.where(and_(*filters))
            count_stmt = count_stmt.where(and_(*filters))

        # Get total count
        total = await self.db.execute(count_stmt)
        total_count = total.scalar()

        # Get logs
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        logs = list(result.scalars().all())

        return logs, total_count

    async def get_recent_activity(
        self,
        user_id: Optional[int] = None,
        limit: int = 50
    ) -> List[AuditLog]:
        """
        Get recent activity logs.

        Args:
            user_id: Filter by user (None = all users)
            limit: Maximum results

        Returns:
            List of recent AuditLog entries
        """
        stmt = select(AuditLog)

        if user_id is not None:
            stmt = stmt.where(AuditLog.user_id == user_id)

        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get audit log statistics.

        Args:
            start_date: Start date for statistics
            end_date: End date for statistics

        Returns:
            Dictionary with statistics
        """
        filters = []
        if start_date:
            filters.append(AuditLog.created_at >= start_date)
        if end_date:
            filters.append(AuditLog.created_at <= end_date)

        where_clause = and_(*filters) if filters else None

        # Total logs
        total_stmt = select(func.count()).select_from(AuditLog)
        if where_clause is not None:
            total_stmt = total_stmt.where(where_clause)
        total_result = await self.db.execute(total_stmt)
        total = total_result.scalar()

        # By severity
        severity_stmt = select(
            AuditLog.severity,
            func.count(AuditLog.id).label('count')
        ).group_by(AuditLog.severity)
        if where_clause is not None:
            severity_stmt = severity_stmt.where(where_clause)
        severity_result = await self.db.execute(severity_stmt)
        by_severity = {row.severity: row.count for row in severity_result}

        # By action (top 10)
        action_stmt = select(
            AuditLog.action,
            func.count(AuditLog.id).label('count')
        ).group_by(AuditLog.action).order_by(func.count(AuditLog.id).desc()).limit(10)
        if where_clause is not None:
            action_stmt = action_stmt.where(where_clause)
        action_result = await self.db.execute(action_stmt)
        top_actions = {row.action: row.count for row in action_result}

        # By user (top 10)
        user_stmt = select(
            AuditLog.username,
            func.count(AuditLog.id).label('count')
        ).where(AuditLog.username.isnot(None)).group_by(AuditLog.username).order_by(func.count(AuditLog.id).desc()).limit(10)
        if where_clause is not None:
            user_stmt = user_stmt.where(where_clause)
        user_result = await self.db.execute(user_stmt)
        top_users = {row.username: row.count for row in user_result}

        return {
            "total_logs": total,
            "by_severity": by_severity,
            "top_actions": top_actions,
            "top_users": top_users,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None
        }
