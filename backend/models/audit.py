"""
Audit logging models.

Related: Issue #9 - Enhance audit logging system
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
import enum

from backend.models.base import Base


class AuditSeverity(str, enum.Enum):
    """Audit log severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditAction(str, enum.Enum):
    """Common audit actions for standardization."""

    # Authentication
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    TOKEN_REFRESH = "TOKEN_REFRESH"

    # User Management
    USER_CREATE = "USER_CREATE"
    USER_UPDATE = "USER_UPDATE"
    USER_DELETE = "USER_DELETE"
    ROLE_CHANGE = "ROLE_CHANGE"

    # Backup Operations
    BACKUP_CREATE = "BACKUP_CREATE"
    BACKUP_DELETE = "BACKUP_DELETE"
    BACKUP_RESTORE = "BACKUP_RESTORE"
    BACKUP_VERIFY = "BACKUP_VERIFY"
    BACKUP_MAKE_IMMUTABLE = "BACKUP_MAKE_IMMUTABLE"
    BACKUP_REMOVE_LEGAL_HOLD = "BACKUP_REMOVE_LEGAL_HOLD"

    # VM Operations
    VM_CREATE = "VM_CREATE"
    VM_UPDATE = "VM_UPDATE"
    VM_DELETE = "VM_DELETE"
    VM_START = "VM_START"
    VM_STOP = "VM_STOP"

    # Container Operations
    CONTAINER_CREATE = "CONTAINER_CREATE"
    CONTAINER_UPDATE = "CONTAINER_UPDATE"
    CONTAINER_DELETE = "CONTAINER_DELETE"

    # Storage Operations
    STORAGE_CREATE = "STORAGE_CREATE"
    STORAGE_UPDATE = "STORAGE_UPDATE"
    STORAGE_DELETE = "STORAGE_DELETE"
    STORAGE_TEST = "STORAGE_TEST"

    # Schedule Operations
    SCHEDULE_CREATE = "SCHEDULE_CREATE"
    SCHEDULE_UPDATE = "SCHEDULE_UPDATE"
    SCHEDULE_DELETE = "SCHEDULE_DELETE"
    SCHEDULE_ENABLE = "SCHEDULE_ENABLE"
    SCHEDULE_DISABLE = "SCHEDULE_DISABLE"

    # Encryption/Key Management
    KEY_GENERATE = "KEY_GENERATE"
    KEY_ROTATE = "KEY_ROTATE"
    KEY_EXPORT = "KEY_EXPORT"
    KEY_IMPORT = "KEY_IMPORT"

    # Configuration
    SETTINGS_UPDATE = "SETTINGS_UPDATE"
    CONFIG_CHANGE = "CONFIG_CHANGE"

    # System Events
    SYSTEM_START = "SYSTEM_START"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    DATABASE_MIGRATION = "DATABASE_MIGRATION"

    # API Access
    API_REQUEST = "API_REQUEST"
    API_ERROR = "API_ERROR"


class ResourceType(str, enum.Enum):
    """Resource types for audit logging."""
    USER = "USER"
    BACKUP = "BACKUP"
    VM = "VM"
    CONTAINER = "CONTAINER"
    STORAGE = "STORAGE"
    SCHEDULE = "SCHEDULE"
    JOB = "JOB"
    ENCRYPTION_KEY = "ENCRYPTION_KEY"
    SETTINGS = "SETTINGS"
    KVM_HOST = "KVM_HOST"
    PODMAN_HOST = "PODMAN_HOST"


class AuditLog(Base):
    """Comprehensive audit log for security and compliance."""

    __tablename__ = "audit_logs"

    # User information
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Action details
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    resource_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Request context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    request_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    request_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Response details
    response_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    response_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AuditSeverity.INFO.value,
        index=True
    )
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(50)), nullable=True)
    audit_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column('metadata', JSONB, nullable=True)

    # Relationships
    user: Mapped[Optional["User"]] = relationship(foreign_keys=[user_id], viewonly=True)
