"""
Notification models.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean, JSON, ForeignKey, DateTime, Enum as SQLEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from backend.models.base import Base


class NotificationType(str, enum.Enum):
    """Notification types."""
    EMAIL = "email"
    WEBHOOK = "webhook"


class NotificationEvent(str, enum.Enum):
    """Events that trigger notifications."""
    BACKUP_COMPLETED = "backup_completed"
    BACKUP_FAILED = "backup_failed"
    RESTORE_COMPLETED = "restore_completed"
    RESTORE_FAILED = "restore_failed"
    STORAGE_THRESHOLD = "storage_threshold"
    SCHEDULE_MISSED = "schedule_missed"


class NotificationConfig(Base):
    """User notification configuration."""

    __tablename__ = "notification_configs"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType),
        nullable=False
    )
    events: Mapped[list] = mapped_column(JSON, nullable=False)  # List of NotificationEvent
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="notification_configs")


class Notification(Base):
    """Notification history."""

    __tablename__ = "notifications"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType),
        nullable=False
    )
    event: Mapped[NotificationEvent] = mapped_column(
        SQLEnum(NotificationEvent),
        nullable=False,
        index=True
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta_data: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
