"""
Immutable Backup Service

Provides WORM (Write-Once-Read-Many) protection for backups:
- Retention enforcement
- S3 Object Lock integration
- Deletion protection
- Ransomware protection

Related: Issue #13 - Implement immutable backup support
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.backup import Backup, RetentionMode

logger = logging.getLogger(__name__)


class ImmutabilityError(Exception):
    """Exception raised for immutability errors."""
    pass


class ImmutabilityService:
    """
    Service for managing immutable backups.

    Provides methods for:
    - Calculating retention periods
    - Checking if backup can be deleted
    - Enforcing retention policies
    - Audit logging for deletion attempts
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize immutability service.

        Args:
            db: Async database session
        """
        self.db = db

    async def make_backup_immutable(
        self,
        backup: Backup,
        retention_days: int,
        retention_mode: RetentionMode = RetentionMode.COMPLIANCE,
        reason: Optional[str] = None
    ) -> None:
        """
        Mark a backup as immutable with retention policy.

        Args:
            backup: Backup to make immutable
            retention_days: Number of days to retain (0 = indefinite for LEGAL_HOLD)
            retention_mode: Retention mode (GOVERNANCE, COMPLIANCE, LEGAL_HOLD)
            reason: Human-readable reason for immutability

        Raises:
            ImmutabilityError: If backup is already immutable
        """
        if backup.immutable:
            raise ImmutabilityError(f"Backup {backup.id} is already immutable")

        # Calculate retention_until
        if retention_mode == RetentionMode.LEGAL_HOLD:
            # Legal hold = indefinite retention
            retention_until = None
        else:
            # Calculate expiry date
            if backup.created_at:
                retention_until = backup.created_at + timedelta(days=retention_days)
            else:
                # Fallback to now if created_at not set
                retention_until = datetime.utcnow() + timedelta(days=retention_days)

        # Update backup
        backup.immutable = True
        backup.retention_until = retention_until
        backup.retention_mode = retention_mode.value
        backup.immutability_reason = reason or f"Immutable backup with {retention_days} day retention"

        logger.info(
            f"Marked backup {backup.id} as immutable: "
            f"mode={retention_mode.value}, retention_until={retention_until}"
        )

    async def can_delete_backup(
        self,
        backup_id: int,
        is_admin: bool = False,
        override_governance: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a backup can be deleted.

        Args:
            backup_id: ID of backup to check
            is_admin: Whether user has admin privileges
            override_governance: Whether admin is overriding GOVERNANCE mode

        Returns:
            Tuple of (can_delete, reason)
            - can_delete: True if backup can be deleted
            - reason: Explanation if cannot delete
        """
        # Get backup
        backup = await self.db.get(Backup, backup_id)
        if not backup:
            return False, f"Backup {backup_id} not found"

        # Not immutable - can delete
        if not backup.immutable:
            return True, None

        # Check retention mode
        retention_mode = RetentionMode(backup.retention_mode) if backup.retention_mode else None

        # LEGAL_HOLD: Never deletable
        if retention_mode == RetentionMode.LEGAL_HOLD:
            return False, (
                f"Backup is under LEGAL_HOLD. Legal hold must be removed before deletion. "
                f"Reason: {backup.immutability_reason}"
            )

        # Check if retention has expired
        now = datetime.utcnow()
        retention_expired = backup.retention_until and backup.retention_until <= now

        # COMPLIANCE mode
        if retention_mode == RetentionMode.COMPLIANCE:
            if retention_expired:
                return True, None
            else:
                days_remaining = (backup.retention_until - now).days if backup.retention_until else 0
                return False, (
                    f"Backup is immutable in COMPLIANCE mode. "
                    f"Retention expires in {days_remaining} days ({backup.retention_until}). "
                    f"Reason: {backup.immutability_reason}"
                )

        # GOVERNANCE mode
        if retention_mode == RetentionMode.GOVERNANCE:
            if retention_expired:
                return True, None

            # Admin can override GOVERNANCE mode
            if is_admin and override_governance:
                logger.warning(
                    f"Admin override: Deleting immutable backup {backup_id} "
                    f"in GOVERNANCE mode before retention expires"
                )
                return True, None

            # Non-admin or not overriding
            days_remaining = (backup.retention_until - now).days if backup.retention_until else 0
            return False, (
                f"Backup is immutable in GOVERNANCE mode. "
                f"Retention expires in {days_remaining} days ({backup.retention_until}). "
                f"Admin can override with explicit flag. "
                f"Reason: {backup.immutability_reason}"
            )

        # Unknown retention mode or None
        return True, None

    async def remove_legal_hold(self, backup_id: int) -> None:
        """
        Remove legal hold from a backup.

        Converts LEGAL_HOLD to COMPLIANCE with standard retention.

        Args:
            backup_id: ID of backup

        Raises:
            ImmutabilityError: If backup not under legal hold
        """
        backup = await self.db.get(Backup, backup_id)
        if not backup:
            raise ImmutabilityError(f"Backup {backup_id} not found")

        if not backup.immutable or backup.retention_mode != RetentionMode.LEGAL_HOLD.value:
            raise ImmutabilityError(f"Backup {backup_id} is not under LEGAL_HOLD")

        # Convert to COMPLIANCE with standard retention
        # Use backup schedule retention or default 30 days
        retention_days = 30
        if backup.schedule and backup.schedule.retention_config:
            retention_days = backup.schedule.retention_config.get('daily', {}).get('keep', 30)

        backup.retention_mode = RetentionMode.COMPLIANCE.value
        backup.retention_until = datetime.utcnow() + timedelta(days=retention_days)
        backup.immutability_reason = f"Legal hold removed, converted to COMPLIANCE with {retention_days} day retention"

        logger.info(
            f"Removed legal hold from backup {backup_id}, "
            f"converted to COMPLIANCE until {backup.retention_until}"
        )

    async def get_immutable_backups(
        self,
        expired: Optional[bool] = None
    ) -> list[Backup]:
        """
        Get list of immutable backups.

        Args:
            expired: If True, return only expired backups
                    If False, return only active backups
                    If None, return all immutable backups

        Returns:
            List of immutable Backup objects
        """
        stmt = select(Backup).where(Backup.immutable == True)

        if expired is not None:
            now = datetime.utcnow()
            if expired:
                # Get expired backups (retention_until <= now)
                stmt = stmt.where(
                    Backup.retention_until.isnot(None),
                    Backup.retention_until <= now
                )
            else:
                # Get active backups (retention_until > now or NULL for LEGAL_HOLD)
                stmt = stmt.where(
                    (Backup.retention_until.is_(None)) |
                    (Backup.retention_until > now)
                )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_retention_statistics(self) -> dict:
        """
        Get statistics about immutable backups.

        Returns:
            Dictionary with statistics:
            - total_immutable: Total number of immutable backups
            - compliance_count: Number in COMPLIANCE mode
            - governance_count: Number in GOVERNANCE mode
            - legal_hold_count: Number under LEGAL_HOLD
            - expired_count: Number with expired retention
        """
        immutable_backups = await self.get_immutable_backups()

        stats = {
            "total_immutable": len(immutable_backups),
            "compliance_count": 0,
            "governance_count": 0,
            "legal_hold_count": 0,
            "expired_count": 0
        }

        now = datetime.utcnow()

        for backup in immutable_backups:
            # Count by retention mode
            if backup.retention_mode == RetentionMode.COMPLIANCE.value:
                stats["compliance_count"] += 1
            elif backup.retention_mode == RetentionMode.GOVERNANCE.value:
                stats["governance_count"] += 1
            elif backup.retention_mode == RetentionMode.LEGAL_HOLD.value:
                stats["legal_hold_count"] += 1

            # Count expired
            if backup.retention_until and backup.retention_until <= now:
                stats["expired_count"] += 1

        return stats
