"""
Backup schedule and backup models.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, BigInteger, Boolean, JSON, ForeignKey, DateTime, Enum as SQLEnum, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from backend.models.base import Base


class SourceType(str, enum.Enum):
    """Source type for backups."""
    VM = "vm"
    CONTAINER = "container"


class ScheduleType(str, enum.Enum):
    """Backup schedule types."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    ARCHIVAL = "archival"
    CUSTOM = "custom"


class BackupStatus(str, enum.Enum):
    """Backup job status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackupMode(str, enum.Enum):
    """Backup mode - full or incremental."""
    FULL = "full"
    INCREMENTAL = "incremental"


class RetentionMode(str, enum.Enum):
    """Immutable backup retention modes (Issue #13)."""
    GOVERNANCE = "GOVERNANCE"  # Admin can override deletion
    COMPLIANCE = "COMPLIANCE"  # Cannot delete until retention expires
    LEGAL_HOLD = "LEGAL_HOLD"  # Indefinite retention, must remove hold first


class BackupSchedule(Base):
    """Backup schedule configuration."""

    __tablename__ = "backup_schedules"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[SourceType] = mapped_column(
        SQLEnum(SourceType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    source_id: Mapped[int] = mapped_column(nullable=False, index=True)
    schedule_type: Mapped[ScheduleType] = mapped_column(
        SQLEnum(ScheduleType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    retention_config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    storage_backend_id: Mapped[int] = mapped_column(
        ForeignKey("storage_backends.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_run: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_metadata: Mapped[Optional[dict]] = mapped_column('metadata', JSON, nullable=True)

    # Compliance tracking (Issue #8)
    rpo_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment='Recovery Point Objective in minutes'
    )
    rto_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment='Recovery Time Objective in minutes'
    )

    # Relationships
    storage_backend: Mapped["StorageBackend"] = relationship(back_populates="backup_schedules")
    vm: Mapped[Optional["VM"]] = relationship(
        back_populates="backup_schedules",
        foreign_keys=[source_id],
        primaryjoin="and_(BackupSchedule.source_id==VM.id, BackupSchedule.source_type=='vm')",
        viewonly=True
    )
    container: Mapped[Optional["Container"]] = relationship(
        back_populates="backup_schedules",
        foreign_keys=[source_id],
        primaryjoin="and_(BackupSchedule.source_id==Container.id, BackupSchedule.source_type=='container')",
        viewonly=True
    )
    backups: Mapped[list["Backup"]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan"
    )


class Backup(Base):
    """Individual backup record."""

    __tablename__ = "backups"

    schedule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("backup_schedules.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        SQLEnum(SourceType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    source_id: Mapped[int] = mapped_column(nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    backup_type: Mapped[ScheduleType] = mapped_column(
        SQLEnum(ScheduleType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    backup_mode: Mapped[BackupMode] = mapped_column(
        SQLEnum(BackupMode, values_callable=lambda x: [e.value for e in x]),
        default=BackupMode.FULL,
        nullable=False,
        index=True
    )
    parent_backup_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("backups.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[BackupStatus] = mapped_column(
        SQLEnum(BackupStatus, values_callable=lambda x: [e.value for e in x]),
        default=BackupStatus.PENDING,
        nullable=False,
        index=True
    )
    size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # in bytes
    compressed_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # in bytes
    storage_backend_id: Mapped[int] = mapped_column(
        ForeignKey("storage_backends.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    backup_metadata: Mapped[Optional[dict]] = mapped_column('metadata', JSON, nullable=True)

    # Verification tracking (Issue #6)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    verification_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    verification_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_job_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    verified_table_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    verified_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    verification_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Encryption key tracking (Issue #7)
    encryption_key_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("encryption_keys.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Reference to encryption key used for this backup"
    )
    encryption_scheme: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        default="GLOBAL",
        index=True,
        comment="GLOBAL, STORAGE, VM, or CONTAINER"
    )

    # Backup chain tracking (Issue #10)
    chain_id: Mapped[Optional[str]] = mapped_column(
        String(36),  # UUID as string
        nullable=True,
        index=True,
        comment="UUID grouping related backups (full + incrementals)"
    )
    sequence_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="Position in backup chain (0=first backup, increments for each subsequent)"
    )

    # Deduplication and compression metrics (Issue #10)
    original_size: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Original size in bytes before dedup/compression"
    )
    dedupe_ratio: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Deduplication ratio (original_size / deduplicated_size). Higher is better."
    )
    compression_ratio: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Compression ratio (deduplicated_size / compressed_size). Higher is better."
    )
    space_saved_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Total space saved vs full backup (original_size - compressed_size)"
    )

    # Changed Block Tracking (Issue #15)
    cbt_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Whether this backup used CBT for incremental tracking"
    )
    changed_blocks_count: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Number of changed blocks in incremental backup (0 for full backups)"
    )
    bitmap_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Name of the dirty bitmap used for this backup"
    )
    block_size: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Block size (granularity) used for CBT tracking (bytes)"
    )

    # Application Consistency via Guest Agent (Issue #14)
    application_consistent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Whether this backup was created with application consistency (fsfreeze + scripts)"
    )
    fsfreeze_status: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Status of filesystem freeze: SUCCESS, FAILED, TIMEOUT, NOT_ATTEMPTED"
    )
    script_execution_log: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Log of pre/post backup script execution results"
    )

    # Immutable Backup Support (Issue #13)
    immutable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Whether this backup is immutable (WORM protected)"
    )
    retention_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Timestamp when retention expires and deletion is allowed"
    )
    retention_mode: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Retention mode: GOVERNANCE, COMPLIANCE, LEGAL_HOLD"
    )
    immutability_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Human-readable reason for immutability (compliance, ransomware protection, etc.)"
    )

    # Relationships
    schedule: Mapped[Optional["BackupSchedule"]] = relationship(back_populates="backups")
    storage_backend: Mapped["StorageBackend"] = relationship(back_populates="backups")
    parent_backup: Mapped[Optional["Backup"]] = relationship(
        "Backup",
        remote_side="Backup.id",
        foreign_keys=[parent_backup_id],
        back_populates="child_backups"
    )
    child_backups: Mapped[list["Backup"]] = relationship(
        "Backup",
        foreign_keys=[parent_backup_id],
        back_populates="parent_backup"
    )
    job: Mapped[Optional["Job"]] = relationship(
        back_populates="backup",
        foreign_keys="[Job.backup_id]",
        uselist=False
    )
    verification_job: Mapped[Optional["Job"]] = relationship(
        foreign_keys=[verification_job_id],
        viewonly=True
    )


class JobType(str, enum.Enum):
    """Job types."""
    BACKUP = "backup"
    RESTORE = "restore"
    VERIFICATION = "verification"
    CLEANUP = "cleanup"
    SYNC = "sync"


class JobStatus(str, enum.Enum):
    """Job status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base):
    """Job execution tracking."""

    __tablename__ = "jobs"

    type: Mapped[JobType] = mapped_column(
        SQLEnum(JobType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, values_callable=lambda x: [e.value for e in x]),
        default=JobStatus.PENDING,
        nullable=False,
        index=True
    )
    backup_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("backups.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_metadata: Mapped[Optional[dict]] = mapped_column('metadata', JSON, nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Relationships
    backup: Mapped[Optional["Backup"]] = relationship(
        back_populates="job",
        foreign_keys=[backup_id]
    )
    logs: Mapped[list["JobLog"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan"
    )


class JobLog(Base):
    """Job execution logs."""

    __tablename__ = "job_logs"

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="logs")
