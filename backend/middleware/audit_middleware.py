"""
FastAPI middleware for automatic audit logging of all API requests.

Logs all incoming requests with:
- Request method, path, query parameters, body
- User information (if authenticated)
- Client IP address and user agent
- Response status code
- Request processing duration
- Sanitized request data (passwords/tokens removed)

Related: Issue #9 - Enhance Audit Logging System
"""

import time
import logging
from typing import Callable, Optional, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.models.base import AsyncSessionLocal
from backend.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests for security auditing."""

    # Paths to exclude from audit logging (too noisy)
    EXCLUDED_PATHS = {
        '/health',
        '/metrics',
        '/static',
        '/favicon.ico'
    }

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and log to audit trail.

        Args:
            request: Incoming FastAPI request
            call_next: Next middleware/handler in chain

        Returns:
            Response from handler
        """
        start_time = time.time()

        # Skip audit logging for excluded paths
        if any(request.url.path.startswith(path) for path in self.EXCLUDED_PATHS):
            return await call_next(request)

        # Extract request information
        request_method = request.method
        request_path = request.url.path
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent")

        # Get authenticated user ID if available
        user_id = await self._get_user_id(request)

        # Extract request data (query params + body)
        request_data = await self._extract_request_data(request)

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Log the request asynchronously (don't block response)
        try:
            await self._log_request(
                request_method=request_method,
                request_path=request_path,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_data=request_data,
                response_status=response.status_code,
                duration_ms=duration_ms
            )
        except Exception as e:
            # Don't let logging failures crash the request
            logger.error(f"Failed to log API request: {e}", exc_info=True)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.

        Checks X-Forwarded-For header first (for proxies), then client.host.

        Args:
            request: FastAPI request

        Returns:
            Client IP address
        """
        # Check for proxy headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, get the first one
            return forwarded_for.split(",")[0].strip()

        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"

    async def _get_user_id(self, request: Request) -> Optional[int]:
        """
        Extract authenticated user ID from request.

        Checks request.state.user which is set by authentication middleware.

        Args:
            request: FastAPI request

        Returns:
            User ID if authenticated, None otherwise
        """
        try:
            # The get_current_user dependency sets request.state.user
            if hasattr(request.state, "user") and request.state.user:
                return request.state.user.id
        except Exception:
            pass

        return None

    async def _extract_request_data(self, request: Request) -> Optional[Dict[str, Any]]:
        """
        Extract request data (query params and body).

        Args:
            request: FastAPI request

        Returns:
            Dictionary with query and body data
        """
        try:
            data = {}

            # Add query parameters
            if request.query_params:
                data['query'] = dict(request.query_params)

            # Add request body for POST/PUT/PATCH
            if request.method in ["POST", "PUT", "PATCH"]:
                try:
                    # Try to parse as JSON
                    body = await request.json()
                    data['body'] = body
                except Exception:
                    # Not JSON or already consumed, skip
                    pass

            return data if data else None

        except Exception as e:
            logger.debug(f"Could not extract request data: {e}")
            return None

    async def _log_request(
        self,
        request_method: str,
        request_path: str,
        user_id: Optional[int],
        ip_address: str,
        user_agent: Optional[str],
        request_data: Optional[Dict[str, Any]],
        response_status: int,
        duration_ms: float
    ):
        """
        Create audit log entry for the request.

        Args:
            request_method: HTTP method
            request_path: API endpoint path
            user_id: Authenticated user ID
            ip_address: Client IP
            user_agent: Client user agent
            request_data: Request body/query params
            response_status: HTTP status code
            duration_ms: Request duration
        """
        async with AsyncSessionLocal() as db:
            audit_logger = AuditLogger(db)

            await audit_logger.log_api_request(
                request_method=request_method,
                request_path=request_path,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_data=request_data,
                response_status=response_status,
                duration_ms=duration_ms
            )
