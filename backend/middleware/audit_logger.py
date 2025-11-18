"""
Audit Logging Middleware

Automatically logs all API requests for security and compliance.

Related: Issue #9 - Enhance audit logging system
"""
import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.services.audit import AuditLogService
from backend.models.audit import AuditAction, AuditSeverity
from backend.core.security import decode_token

logger = logging.getLogger(__name__)


class AuditLoggerMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically log all API requests.

    Captures:
    - User information (from JWT token)
    - Request details (method, path, client IP, user agent)
    - Response status and duration
    - Errors and exceptions
    """

    # Paths to exclude from audit logging (health checks, metrics, etc.)
    EXCLUDED_PATHS = {
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc"
    }

    # Paths that should be logged with higher severity
    CRITICAL_PATHS = {
        "/api/v1/users",
        "/api/v1/backups/*/immutable",
        "/api/v1/backups/*/legal-hold",
        "/api/v1/storage",
        "/api/v1/encryption/keys"
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and log to audit system.

        Args:
            request: FastAPI request
            call_next: Next middleware/route handler

        Returns:
            Response from route handler
        """
        # Skip excluded paths
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Start timing
        start_time = time.time()

        # Extract user information from JWT token
        user_id = None
        username = None
        try:
            # Try to get Authorization header
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                payload = decode_token(token)
                if payload:
                    user_id = payload.get("sub")  # User ID from JWT
                    username = payload.get("username")
        except Exception:
            # If token decode fails, continue without user info
            pass

        # Extract request info
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        request_method = request.method
        request_path = request.url.path

        # Try to get request body (for POST/PUT/PATCH)
        request_data = None
        if request_method in ["POST", "PUT", "PATCH"]:
            try:
                # Read body (be careful with large payloads)
                body = await request.body()
                if body and len(body) < 10000:  # Limit to 10KB
                    import json
                    request_data = json.loads(body.decode('utf-8'))
            except Exception as e:
                logger.debug(f"Could not parse request body: {e}")

        # Process request
        response = None
        response_status = None
        response_message = None
        severity = AuditSeverity.INFO.value

        try:
            response = await call_next(request)
            response_status = response.status_code

            # Determine severity based on status code
            if response_status >= 500:
                severity = AuditSeverity.ERROR.value
            elif response_status >= 400:
                severity = AuditSeverity.WARNING.value

        except Exception as e:
            # Log exceptions
            response_status = 500
            response_message = str(e)
            severity = AuditSeverity.CRITICAL.value
            logger.error(f"Request failed with exception: {e}", exc_info=True)
            raise

        finally:
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Determine action based on method and path
            action = self._determine_action(request_method, request_path)

            # Determine if this is a critical operation
            if any(critical in request_path for critical in self.CRITICAL_PATHS):
                severity = AuditSeverity.WARNING.value if severity == AuditSeverity.INFO.value else severity

            # Log to audit system (async, don't block response)
            try:
                await self._log_to_audit(
                    action=action,
                    user_id=user_id,
                    username=username,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_method=request_method,
                    request_path=request_path,
                    request_data=request_data,
                    response_status=response_status,
                    response_message=response_message,
                    duration_ms=duration_ms,
                    severity=severity
                )
            except Exception as e:
                # Don't let audit logging failure break the request
                logger.error(f"Failed to log audit entry: {e}", exc_info=True)

        return response

    def _determine_action(self, method: str, path: str) -> str:
        """
        Determine audit action from HTTP method and path.

        Args:
            method: HTTP method
            path: Request path

        Returns:
            Action string
        """
        # Map method to generic action
        method_actions = {
            "GET": "API_REQUEST",
            "POST": "API_REQUEST",
            "PUT": "API_REQUEST",
            "PATCH": "API_REQUEST",
            "DELETE": "API_REQUEST"
        }

        # Try to determine specific action from path
        if "/login" in path:
            return AuditAction.LOGIN_SUCCESS.value if method == "POST" else "API_REQUEST"
        elif "/backups" in path and method == "POST":
            return AuditAction.BACKUP_CREATE.value
        elif "/backups" in path and method == "DELETE":
            return AuditAction.BACKUP_DELETE.value
        elif "/restore" in path:
            return AuditAction.BACKUP_RESTORE.value
        elif "/users" in path and method == "POST":
            return AuditAction.USER_CREATE.value
        elif "/users" in path and method == "DELETE":
            return AuditAction.USER_DELETE.value
        elif "/storage" in path and method == "POST":
            return AuditAction.STORAGE_CREATE.value
        elif "/storage" in path and method == "DELETE":
            return AuditAction.STORAGE_DELETE.value

        return method_actions.get(method, AuditAction.API_REQUEST.value)

    async def _log_to_audit(
        self,
        action: str,
        user_id: Optional[int],
        username: Optional[str],
        ip_address: Optional[str],
        user_agent: Optional[str],
        request_method: str,
        request_path: str,
        request_data: Optional[dict],
        response_status: int,
        response_message: Optional[str],
        duration_ms: int,
        severity: str
    ):
        """
        Log request to audit system.

        Creates a new database session for audit logging.
        """
        # Create new database session for audit logging
        async for db in get_db():
            try:
                audit_service = AuditLogService(db)
                await audit_service.log(
                    action=action,
                    user_id=user_id,
                    username=username,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_method=request_method,
                    request_path=request_path,
                    request_data=request_data,
                    response_status=response_status,
                    response_message=response_message,
                    duration_ms=duration_ms,
                    severity=severity,
                    tags=["api", request_method.lower()]
                )
            except Exception as e:
                logger.error(f"Failed to create audit log: {e}", exc_info=True)
            finally:
                await db.close()
                break  # Only use first session from generator
