"""
Centralized audit logging service for security events and API requests.

Provides consistent audit logging across the application with:
- Data sanitization (removes passwords, keys, tokens)
- Severity levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- SIEM-ready event formatting
- Async database logging

Related: Issue #9 - Enhance Audit Logging System
"""

import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import AuditLog

logger = logging.getLogger(__name__)


class AuditSeverity:
    """Audit log severity levels for SIEM integration."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditLogger:
    """Service for creating audit log entries."""

    # Sensitive field names to sanitize
    SENSITIVE_FIELDS = {
        'password', 'password_hash', 'token', 'api_key', 'secret', 'key',
        'private_key', 'access_token', 'refresh_token', 'auth_token',
        'encryption_key', 'passphrase', 'credentials', 'authorization'
    }

    def __init__(self, db: AsyncSession):
        """
        Initialize audit logger.

        Args:
            db: Database session
        """
        self.db = db

    @staticmethod
    def sanitize_data(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Sanitize sensitive data before logging.

        Replaces passwords, tokens, keys, etc. with '***REDACTED***'.

        Args:
            data: Dictionary to sanitize

        Returns:
            Sanitized dictionary
        """
        if data is None:
            return None

        if not isinstance(data, dict):
            return data

        sanitized = {}
        for key, value in data.items():
            key_lower = key.lower()

            # Check if key contains sensitive field name
            is_sensitive = any(
                sensitive in key_lower
                for sensitive in AuditLogger.SENSITIVE_FIELDS
            )

            if is_sensitive:
                sanitized[key] = '***REDACTED***'
            elif isinstance(value, dict):
                sanitized[key] = AuditLogger.sanitize_data(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    AuditLogger.sanitize_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    async def log_event(
        self,
        action: str,
        user_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        response_status: Optional[int] = None,
        duration_ms: Optional[float] = None,
        severity: str = AuditSeverity.INFO
    ) -> AuditLog:
        """
        Create an audit log entry.

        Args:
            action: Action performed (e.g., "LOGIN_SUCCESS", "CREATE_BACKUP")
            user_id: ID of user who performed the action
            resource_type: Type of resource affected (e.g., "VM", "BACKUP", "USER")
            resource_id: ID of affected resource
            details: Additional context (will be sanitized)
            ip_address: Client IP address
            user_agent: Client user agent string
            request_method: HTTP method (GET, POST, etc.)
            request_path: API endpoint path
            request_data: Request body/query parameters (will be sanitized)
            response_status: HTTP response status code
            duration_ms: Request processing duration
            severity: Log severity level

        Returns:
            Created AuditLog instance
        """
        try:
            # Sanitize sensitive data
            sanitized_details = self.sanitize_data(details)
            sanitized_request_data = self.sanitize_data(request_data)

            # Create audit log entry
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=sanitized_details,
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=request_method,
                request_path=request_path,
                request_data=sanitized_request_data,
                response_status=response_status,
                duration_ms=duration_ms,
                severity=severity
            )

            self.db.add(audit_log)
            await self.db.commit()
            await self.db.refresh(audit_log)

            logger.debug(
                f"Audit log created: {action} "
                f"(user_id={user_id}, severity={severity}, status={response_status})"
            )

            # Export to SIEM if configured (Issue #9)
            try:
                from backend.services.siem_integration import get_siem_integration
                siem = get_siem_integration()
                if siem:
                    siem.export_audit_log(audit_log)
            except Exception as e:
                # Don't let SIEM export failures crash audit logging
                logger.warning(f"Failed to export audit log to SIEM: {e}")

            return audit_log

        except Exception as e:
            logger.error(f"Failed to create audit log: {e}", exc_info=True)
            # Don't let audit logging failures crash the application
            await self.db.rollback()
            raise

    async def log_authentication(
        self,
        action: str,
        username: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Log authentication events (login, logout, password change).

        Args:
            action: Action type (LOGIN, LOGOUT, PASSWORD_CHANGE, etc.)
            username: Username attempting authentication
            success: Whether authentication succeeded
            ip_address: Client IP address
            user_agent: Client user agent
            details: Additional context

        Returns:
            Created AuditLog instance
        """
        severity = AuditSeverity.INFO if success else AuditSeverity.WARNING

        audit_details = {
            'username': username,
            'success': success,
            **(details or {})
        }

        return await self.log_event(
            action=f"AUTH_{action}_{'SUCCESS' if success else 'FAILURE'}",
            resource_type="AUTHENTICATION",
            details=audit_details,
            ip_address=ip_address,
            user_agent=user_agent,
            severity=severity
        )

    async def log_configuration_change(
        self,
        action: str,
        user_id: int,
        resource_type: str,
        resource_id: Optional[int] = None,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log configuration changes.

        Args:
            action: Action type (CREATE, UPDATE, DELETE)
            user_id: User making the change
            resource_type: Type of resource (STORAGE, SCHEDULE, SETTING, etc.)
            resource_id: ID of resource
            old_value: Previous value (will be sanitized)
            new_value: New value (will be sanitized)
            ip_address: Client IP address

        Returns:
            Created AuditLog instance
        """
        details = {}
        if old_value is not None:
            details['old_value'] = old_value
        if new_value is not None:
            details['new_value'] = new_value

        return await self.log_event(
            action=f"CONFIG_{action}_{resource_type}",
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            severity=AuditSeverity.INFO
        )

    async def log_backup_operation(
        self,
        action: str,
        user_id: Optional[int],
        backup_id: Optional[int],
        source_type: str,
        source_id: int,
        source_name: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Log backup/restore operations.

        Args:
            action: Action type (BACKUP_CREATE, BACKUP_DELETE, RESTORE, etc.)
            user_id: User initiating the operation
            backup_id: Backup ID (if applicable)
            source_type: Source type (VM or CONTAINER)
            source_id: Source ID
            source_name: Source name
            success: Whether operation succeeded
            details: Additional context

        Returns:
            Created AuditLog instance
        """
        severity = AuditSeverity.INFO if success else AuditSeverity.ERROR

        audit_details = {
            'source_type': source_type,
            'source_id': source_id,
            'source_name': source_name,
            'success': success,
            **(details or {})
        }

        return await self.log_event(
            action=f"BACKUP_{action}_{'SUCCESS' if success else 'FAILURE'}",
            user_id=user_id,
            resource_type="BACKUP",
            resource_id=backup_id,
            details=audit_details,
            severity=severity
        )

    async def log_encryption_operation(
        self,
        action: str,
        user_id: int,
        key_type: str,
        key_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Log encryption key operations.

        Args:
            action: Action type (GENERATE, ROTATE, EXPORT, IMPORT, etc.)
            user_id: User performing the operation
            key_type: Type of key (GLOBAL, STORAGE_BACKEND, VM, CONTAINER)
            key_id: Encryption key ID
            details: Additional context (will be sanitized)

        Returns:
            Created AuditLog instance
        """
        audit_details = {
            'key_type': key_type,
            **(details or {})
        }

        return await self.log_event(
            action=f"ENCRYPTION_{action}",
            user_id=user_id,
            resource_type="ENCRYPTION_KEY",
            resource_id=key_id,
            details=audit_details,
            severity=AuditSeverity.WARNING  # Encryption operations are security-sensitive
        )

    async def log_api_request(
        self,
        request_method: str,
        request_path: str,
        user_id: Optional[int],
        ip_address: str,
        user_agent: Optional[str],
        request_data: Optional[Dict[str, Any]],
        response_status: int,
        duration_ms: float,
        error: Optional[str] = None
    ) -> AuditLog:
        """
        Log API requests (called from middleware).

        Args:
            request_method: HTTP method
            request_path: API endpoint path
            user_id: Authenticated user ID
            ip_address: Client IP
            user_agent: Client user agent
            request_data: Request body/query params
            response_status: HTTP status code
            duration_ms: Request duration
            error: Error message if request failed

        Returns:
            Created AuditLog instance
        """
        # Determine severity based on status code
        if response_status >= 500:
            severity = AuditSeverity.ERROR
        elif response_status >= 400:
            severity = AuditSeverity.WARNING
        else:
            severity = AuditSeverity.INFO

        details = {}
        if error:
            details['error'] = error

        return await self.log_event(
            action=f"API_{request_method}",
            user_id=user_id,
            details=details if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            request_data=request_data,
            response_status=response_status,
            duration_ms=duration_ms,
            severity=severity
        )
