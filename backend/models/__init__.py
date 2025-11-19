"""
Database models package.
"""
from backend.models.base import Base, get_db
from backend.models.user import User, UserRole, APIToken
from backend.models.audit import AuditLog
from backend.models.infrastructure import KVMHost, VM, PodmanHost, Container
from backend.models.encryption import EncryptionKey
from backend.models.storage import StorageBackend, StorageType
from backend.models.backup import (
    BackupSchedule,
    Backup,
    Job,
    JobLog,
    SourceType,
    ScheduleType,
    BackupStatus,
    BackupMode,
    JobType,
    JobStatus
)
from backend.models.notification import (
    NotificationConfig,
    Notification,
    NotificationType,
    NotificationEvent
)
from backend.models.settings import SystemSetting

__all__ = [
    # Base
    "Base",
    "get_db",
    # Users
    "User",
    "UserRole",
    "APIToken",
    "AuditLog",
    # Infrastructure
    "KVMHost",
    "VM",
    "PodmanHost",
    "Container",
    # Encryption
    "EncryptionKey",
    # Storage
    "StorageBackend",
    "StorageType",
    # Backups
    "BackupSchedule",
    "Backup",
    "Job",
    "JobLog",
    "SourceType",
    "ScheduleType",
    "BackupStatus",
    "BackupMode",
    "JobType",
    "JobStatus",
    # Notifications
    "NotificationConfig",
    "Notification",
    "NotificationType",
    "NotificationEvent",
    # Settings
    "SystemSetting",
]
