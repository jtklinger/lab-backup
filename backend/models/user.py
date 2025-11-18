"""
User and authentication related models.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Enum as SQLEnum, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from backend.models.base import Base


class UserRole(str, enum.Enum):
    """User roles for RBAC."""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(Base):
    """User model for authentication and authorization."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.VIEWER,
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    api_tokens: Mapped[list["APIToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )
    notification_configs: Mapped[list["NotificationConfig"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="user"
    )


class APIToken(Base):
    """API tokens for programmatic access."""

    __tablename__ = "api_tokens"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="api_tokens")


class AuditLog(Base):
    """Audit log for tracking user actions and API requests."""

    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # API request logging fields (Issue #9)
    request_method: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment='HTTP method (GET, POST, PUT, DELETE, etc.)'
    )
    request_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment='API endpoint path'
    )
    request_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment='Sanitized request body/query parameters'
    )
    response_status: Mapped[Optional[int]] = mapped_column(
        nullable=True,
        comment='HTTP response status code'
    )
    duration_ms: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment='Request processing duration in milliseconds'
    )
    severity: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        default='INFO',
        comment='Log severity (DEBUG, INFO, WARNING, ERROR, CRITICAL)'
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")
