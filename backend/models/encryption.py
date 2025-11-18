"""
Encryption key management models.

This module defines the database models for storing and managing encryption keys.
Keys are stored encrypted using a master KEK (Key Encryption Key) from .env.
"""
from datetime import datetime
from typing import Optional, Dict, Any
import enum

from sqlalchemy import String, Integer, Boolean, JSON, LargeBinary, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class EncryptionKeyType(str, enum.Enum):
    """Types of encryption keys supported."""
    GLOBAL = "global"                  # System-wide default key
    STORAGE_BACKEND = "storage_backend"  # Per-storage-backend key
    VM = "vm"                          # Per-VM key
    CONTAINER = "container"            # Per-container key


class EncryptionKey(Base):
    """
    Encryption key storage model.

    Keys are stored encrypted using the master KEK from ENCRYPTION_KEY in .env.
    This provides secure key storage while enabling database-based disaster recovery.

    Attributes:
        key_type: Type of encryption key (GLOBAL, STORAGE_BACKEND, VM, CONTAINER)
        reference_id: ID of related entity (storage_backend_id, vm_id, container_id)
                     NULL for GLOBAL keys
        encrypted_key: The DEK (Data Encryption Key) encrypted with master KEK
        key_version: Version number, incremented on rotation
        algorithm: Encryption algorithm used (default: Fernet)
        active: Whether this key is currently active (False after rotation)
        created_at: When the key was created
        rotated_at: When the key was rotated (replaced with newer version)
        metadata: Additional key metadata (JSON)
    """

    __tablename__ = "encryption_keys"

    key_type: Mapped[EncryptionKeyType] = mapped_column(
        SQLEnum(EncryptionKeyType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    reference_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="ID of storage_backend/VM/container (NULL for GLOBAL)"
    )
    encrypted_key: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        comment="DEK encrypted with master KEK from .env"
    )
    key_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Increments on rotation"
    )
    algorithm: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Fernet",
        comment="Encryption algorithm used"
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether this key is currently active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    rotated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this key was rotated (replaced)"
    )
    key_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        'metadata',
        JSON,
        nullable=True,
        comment="Additional key metadata"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<EncryptionKey(id={self.id}, type={self.key_type}, version={self.key_version}, active={self.active})>"
