"""
Retention policy engine implementing grandfather-father-son rotation.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from backend.models.backup import Backup, ScheduleType, BackupStatus

logger = logging.getLogger(__name__)


class RetentionPolicy:
    """
    Implements grandfather-father-son (GFS) backup retention strategy.

    Strategy:
    - Daily (Son): Keep last N daily backups
    - Weekly (Father): Keep last N weekly backups (first backup of week)
    - Monthly (Grandfather): Keep last N monthly backups (first backup of month)
    - Yearly: Keep last N yearly backups (first backup of year)
    - Archival: Keep indefinitely (manual deletion only)
    """

    def __init__(
        self,
        daily_retention: int = 7,
        weekly_retention: int = 4,
        monthly_retention: int = 12,
        yearly_retention: int = 5
    ):
        """
        Initialize retention policy.

        Args:
            daily_retention: Number of daily backups to keep
            weekly_retention: Number of weekly backups to keep
            monthly_retention: Number of monthly backups to keep
            yearly_retention: Number of yearly backups to keep
        """
        self.daily_retention = daily_retention
        self.weekly_retention = weekly_retention
        self.monthly_retention = monthly_retention
        self.yearly_retention = yearly_retention

    async def evaluate_backups(
        self,
        db: AsyncSession,
        schedule_id: int,
        config: Dict[str, Any]
    ) -> List[int]:
        """
        Evaluate backups and return IDs of backups that should be deleted.

        Args:
            db: Database session
            schedule_id: ID of the backup schedule
            config: Retention configuration override

        Returns:
            List of backup IDs to delete
        """
        # Get retention settings (use config override if provided)
        daily_keep = config.get("daily", self.daily_retention)
        weekly_keep = config.get("weekly", self.weekly_retention)
        monthly_keep = config.get("monthly", self.monthly_retention)
        yearly_keep = config.get("yearly", self.yearly_retention)

        # Fetch all completed backups for this schedule, ordered by completion time
        stmt = select(Backup).where(
            Backup.schedule_id == schedule_id,
            Backup.status == BackupStatus.COMPLETED
        ).order_by(Backup.completed_at.desc())

        result = await db.execute(stmt)
        all_backups = result.scalars().all()

        if not all_backups:
            return []

        # Categorize backups
        backups_to_keep = set()
        now = datetime.utcnow()

        # Categorize by type
        daily_backups = []
        weekly_backups = []
        monthly_backups = []
        yearly_backups = []
        archival_backups = []

        for backup in all_backups:
            if backup.backup_type == ScheduleType.DAILY or not backup.backup_type:
                daily_backups.append(backup)
            elif backup.backup_type == ScheduleType.WEEKLY:
                weekly_backups.append(backup)
            elif backup.backup_type == ScheduleType.MONTHLY:
                monthly_backups.append(backup)
            elif backup.backup_type == ScheduleType.YEARLY:
                yearly_backups.append(backup)
            elif backup.backup_type == ScheduleType.ARCHIVAL:
                archival_backups.append(backup)

        # Keep daily backups
        for backup in daily_backups[:daily_keep]:
            backups_to_keep.add(backup.id)

        # Keep weekly backups (first backup of each week)
        weekly_map = {}
        for backup in all_backups:
            if backup.completed_at:
                week_key = backup.completed_at.isocalendar()[:2]  # (year, week)
                if week_key not in weekly_map:
                    weekly_map[week_key] = backup

        weekly_sorted = sorted(
            weekly_map.values(),
            key=lambda b: b.completed_at,
            reverse=True
        )
        for backup in weekly_sorted[:weekly_keep]:
            backups_to_keep.add(backup.id)

        # Keep monthly backups (first backup of each month)
        monthly_map = {}
        for backup in all_backups:
            if backup.completed_at:
                month_key = (backup.completed_at.year, backup.completed_at.month)
                if month_key not in monthly_map:
                    monthly_map[month_key] = backup

        monthly_sorted = sorted(
            monthly_map.values(),
            key=lambda b: b.completed_at,
            reverse=True
        )
        for backup in monthly_sorted[:monthly_keep]:
            backups_to_keep.add(backup.id)

        # Keep yearly backups (first backup of each year)
        yearly_map = {}
        for backup in all_backups:
            if backup.completed_at:
                year_key = backup.completed_at.year
                if year_key not in yearly_map:
                    yearly_map[year_key] = backup

        yearly_sorted = sorted(
            yearly_map.values(),
            key=lambda b: b.completed_at,
            reverse=True
        )
        for backup in yearly_sorted[:yearly_keep]:
            backups_to_keep.add(backup.id)

        # Always keep archival backups
        for backup in archival_backups:
            backups_to_keep.add(backup.id)

        # Also keep explicitly tagged yearly/monthly/weekly backups
        for backup in yearly_backups:
            backups_to_keep.add(backup.id)
        for backup in monthly_backups:
            backups_to_keep.add(backup.id)
        for backup in weekly_backups:
            backups_to_keep.add(backup.id)

        # Determine backups to delete
        backups_to_delete = [
            backup.id for backup in all_backups
            if backup.id not in backups_to_keep
        ]

        logger.info(
            f"Retention evaluation for schedule {schedule_id}: "
            f"{len(all_backups)} total, "
            f"{len(backups_to_keep)} to keep, "
            f"{len(backups_to_delete)} to delete"
        )

        return backups_to_delete

    async def apply_retention(
        self,
        db: AsyncSession,
        schedule_id: int,
        config: Dict[str, Any],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Apply retention policy to backups.

        Args:
            db: Database session
            schedule_id: ID of the backup schedule
            config: Retention configuration
            dry_run: If True, don't actually delete backups

        Returns:
            Dictionary with results
        """
        backups_to_delete = await self.evaluate_backups(db, schedule_id, config)

        if not backups_to_delete:
            return {
                "deleted_count": 0,
                "deleted_ids": [],
                "dry_run": dry_run
            }

        if dry_run:
            return {
                "deleted_count": len(backups_to_delete),
                "deleted_ids": backups_to_delete,
                "dry_run": True
            }

        # Mark backups for deletion (don't delete immediately)
        # This allows for a grace period and cleanup jobs
        expired_at = datetime.utcnow()

        for backup_id in backups_to_delete:
            stmt = select(Backup).where(Backup.id == backup_id)
            result = await db.execute(stmt)
            backup = result.scalar_one_or_none()

            if backup:
                backup.expires_at = expired_at
                logger.info(f"Marked backup {backup_id} for deletion")

        await db.commit()

        return {
            "deleted_count": len(backups_to_delete),
            "deleted_ids": backups_to_delete,
            "dry_run": False
        }

    def calculate_expiration_date(
        self,
        backup_type: ScheduleType,
        created_at: datetime,
        config: Dict[str, Any]
    ) -> datetime | None:
        """
        Calculate expiration date for a backup based on its type.

        Args:
            backup_type: Type of backup
            created_at: When the backup was created
            config: Retention configuration

        Returns:
            Expiration datetime or None for archival backups
        """
        if backup_type == ScheduleType.ARCHIVAL:
            return None  # Never expires

        retention_days = {
            ScheduleType.DAILY: config.get("daily", self.daily_retention),
            ScheduleType.WEEKLY: config.get("weekly", self.weekly_retention) * 7,
            ScheduleType.MONTHLY: config.get("monthly", self.monthly_retention) * 30,
            ScheduleType.YEARLY: config.get("yearly", self.yearly_retention) * 365,
        }

        days = retention_days.get(backup_type, self.daily_retention)
        return created_at + timedelta(days=days)

    async def get_expired_backups(
        self,
        db: AsyncSession,
        grace_period_hours: int = 24
    ) -> List[Backup]:
        """
        Get backups that have expired and are past the grace period.

        Args:
            db: Database session
            grace_period_hours: Hours to wait after expiration before deletion

        Returns:
            List of expired backups
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=grace_period_hours)

        stmt = select(Backup).where(
            Backup.expires_at <= cutoff_time,
            Backup.status == BackupStatus.COMPLETED
        )

        result = await db.execute(stmt)
        return result.scalars().all()
