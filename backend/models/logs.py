"""
Logging models for application and system logs.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ApplicationLog(Base):
    """
    Application-wide logs for system events, errors, and debugging.
    Separate from JobLog which tracks job-specific execution.
    """

    __tablename__ = "application_logs"

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.now().astimezone().tzinfo),
        nullable=False,
        index=True
    )
    level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True
    )  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    logger: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )  # Logger name (e.g., 'backend.services.kvm')
    message: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    function: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    line_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pathname: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    exception: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Context fields for filtering/correlation
    job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    backup_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    __table_args__ = (
        # Composite index for common queries
        Index('ix_app_logs_timestamp_level', 'timestamp', 'level'),
        Index('ix_app_logs_logger_level', 'logger', 'level'),
    )

    def __repr__(self):
        return f"<ApplicationLog(id={self.id}, level={self.level}, logger={self.logger}, message={self.message[:50]}...)>"
