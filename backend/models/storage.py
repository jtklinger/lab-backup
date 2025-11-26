"""
Storage backend models.
"""
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, Boolean, JSON, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
import enum

from backend.models.base import Base


class StorageType(str, enum.Enum):
    """Storage backend types."""
    LOCAL = "local"
    SMB = "smb"
    NFS = "nfs"
    S3 = "s3"


class EncryptionStrategy(str, enum.Enum):
    """Encryption strategy for storage backends."""
    DISABLED = "DISABLED"  # No encryption
    GLOBAL = "GLOBAL"  # Use global encryption key (backward compatibility)
    APP_LEVEL = "APP_LEVEL"  # Application-level encryption with backend-specific key
    STORAGE_NATIVE = "STORAGE_NATIVE"  # Cloud-native encryption (S3 SSE, etc.)


class StorageBackend(Base):
    """Storage backend configuration."""

    __tablename__ = "storage_backends"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    type: Mapped[StorageType] = mapped_column(
        SQLEnum(StorageType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in GB (auto-detected or from quota)
    used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in GB
    quota_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Manual quota limit in GB
    threshold: Mapped[int] = mapped_column(Integer, default=80, nullable=False)  # Alert threshold percentage
    last_check: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Per-Storage Encryption (Issue #11)
    encryption_strategy: Mapped[EncryptionStrategy] = mapped_column(
        SQLEnum(EncryptionStrategy, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=EncryptionStrategy.GLOBAL,
        index=True,
        comment='Encryption strategy: DISABLED, GLOBAL, APP_LEVEL, STORAGE_NATIVE'
    )
    encryption_key_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("encryption_keys.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment='Encryption key for APP_LEVEL strategy (FK to encryption_keys)'
    )
    encryption_config: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment='Encryption configuration (SSE-KMS ARN, customer keys, etc.)'
    )

    # Relationships
    encryption_key: Mapped[Optional["EncryptionKey"]] = relationship(
        "EncryptionKey",
        foreign_keys=[encryption_key_id]
    )
    backup_schedules: Mapped[list["BackupSchedule"]] = relationship(
        back_populates="storage_backend"
    )
    backups: Mapped[list["Backup"]] = relationship(
        back_populates="storage_backend"
    )
