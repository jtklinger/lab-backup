"""
Database models package.
"""
from backend.models.base import Base, get_db
from backend.models.user import User, UserRole, APIToken, AuditLog
from backend.models.infrastructure import KVMHost, VM, PodmanHost, Container
from backend.models.storage import StorageBackend, StorageType
from backend.models.backup import (
    BackupSchedule,
    Backup,
    Job,
    JobLog,
    SourceType,
    ScheduleType,
    BackupStatus,
    JobType,
    JobStatus
)
from backend.models.notification import (
    NotificationConfig,
    Notification,
    NotificationType,
    NotificationEvent
)

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
    "JobType",
    "JobStatus",
    # Notifications
    "NotificationConfig",
    "Notification",
    "NotificationType",
    "NotificationEvent",
]
