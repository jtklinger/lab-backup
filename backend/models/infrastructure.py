"""
Infrastructure models for KVM hosts, VMs, Podman hosts, and containers.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, JSON, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.models.base import Base


class KVMHost(Base):
    """KVM/libvirt host configuration."""

    __tablename__ = "kvm_hosts"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    uri: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    auth_type: Mapped[str] = mapped_column(
        String(50),
        default="ssh",
        nullable=False
    )  # ssh, tls, local
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_sync: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationships
    vms: Mapped[list["VM"]] = relationship(
        back_populates="kvm_host",
        cascade="all, delete-orphan"
    )
    ssh_keys: Mapped[list["SSHKey"]] = relationship(
        back_populates="kvm_host",
        cascade="all, delete-orphan"
    )


class SSHKey(Base):
    """SSH key for KVM host authentication."""

    __tablename__ = "ssh_keys"

    kvm_host_id: Mapped[int] = mapped_column(
        ForeignKey("kvm_hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    private_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_type: Mapped[str] = mapped_column(String(50), nullable=False)  # rsa, ed25519, etc.
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    kvm_host: Mapped["KVMHost"] = relationship(back_populates="ssh_keys")


class VM(Base):
    """Virtual machine tracked for backup."""

    __tablename__ = "vms"

    kvm_host_id: Mapped[int] = mapped_column(
        ForeignKey("kvm_hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    vcpus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    memory: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in MB
    disk_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in GB
    state: Mapped[str] = mapped_column(String(50), nullable=True)
    vm_metadata: Mapped[Optional[dict]] = mapped_column('metadata', JSON, nullable=True)

    # Relationships
    kvm_host: Mapped["KVMHost"] = relationship(back_populates="vms")
    backup_schedules: Mapped[list["BackupSchedule"]] = relationship(
        back_populates="vm",
        foreign_keys="[BackupSchedule.source_id]",
        viewonly=True,
        primaryjoin="and_(VM.id==BackupSchedule.source_id, BackupSchedule.source_type=='vm')"
    )


class PodmanHost(Base):
    """Podman host configuration."""

    __tablename__ = "podman_hosts"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    uri: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_sync: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationships
    containers: Mapped[list["Container"]] = relationship(
        back_populates="podman_host",
        cascade="all, delete-orphan"
    )


class Container(Base):
    """Podman container tracked for backup."""

    __tablename__ = "containers"

    podman_host_id: Mapped[int] = mapped_column(
        ForeignKey("podman_hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    container_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    image: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=True)
    container_metadata: Mapped[Optional[dict]] = mapped_column('metadata', JSON, nullable=True)

    # Relationships
    podman_host: Mapped["PodmanHost"] = relationship(back_populates="containers")
    backup_schedules: Mapped[list["BackupSchedule"]] = relationship(
        back_populates="container",
        foreign_keys="[BackupSchedule.source_id]",
        viewonly=True,
        primaryjoin="and_(Container.id==BackupSchedule.source_id, BackupSchedule.source_type=='container')"
    )
