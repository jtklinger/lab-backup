"""
Storage backend models.
"""
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from backend.models.base import Base


class StorageType(str, enum.Enum):
    """Storage backend types."""
    LOCAL = "local"
    SMB = "smb"
    NFS = "nfs"
    S3 = "s3"


class StorageBackend(Base):
    """Storage backend configuration."""

    __tablename__ = "storage_backends"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    type: Mapped[StorageType] = mapped_column(
        SQLEnum(StorageType),
        nullable=False,
        index=True
    )
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in GB
    used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in GB
    threshold: Mapped[int] = mapped_column(Integer, default=80, nullable=False)  # percentage
    last_check: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationships
    backup_schedules: Mapped[list["BackupSchedule"]] = relationship(
        back_populates="storage_backend"
    )
    backups: Mapped[list["Backup"]] = relationship(
        back_populates="storage_backend"
    )
