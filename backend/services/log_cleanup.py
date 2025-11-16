"""
Log cleanup service for managing log retention policies.
"""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import AsyncSessionLocal
from backend.models.logs import ApplicationLog
from backend.models.settings import SystemSetting

logger = logging.getLogger(__name__)


async def get_logging_settings(db: AsyncSession) -> dict:
    """Get logging configuration from system settings."""
    settings_keys = [
        'logging.retention_days',
        'logging.error_retention_days',
    ]

    settings = {}
    for key in settings_keys:
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        result = await db.execute(stmt)
        setting = result.scalar_one_or_none()
        if setting:
            settings[key] = setting.get_typed_value()

    # Set defaults if not found
    settings.setdefault('logging.retention_days', 30)
    settings.setdefault('logging.error_retention_days', 90)

    return settings


async def cleanup_application_logs(db: AsyncSession = None) -> dict:
    """
    Clean up old application logs based on retention settings.

    Returns:
        dict: Cleanup statistics
    """
    close_session = False
    if db is None:
        db = AsyncSessionLocal()
        close_session = True

    try:
        # Get retention settings
        settings = await get_logging_settings(db)
        retention_days = settings['logging.retention_days']
        error_retention_days = settings['logging.error_retention_days']

        now = datetime.now(timezone.utc)
        general_cutoff = now - timedelta(days=retention_days)
        error_cutoff = now - timedelta(days=error_retention_days)

        logger.info(f"Starting log cleanup: retention={retention_days}d, error_retention={error_retention_days}d")

        # Delete general logs (INFO, DEBUG, WARNING) older than retention_days
        general_stmt = delete(ApplicationLog).where(
            ApplicationLog.timestamp < general_cutoff,
            ApplicationLog.level.in_(['DEBUG', 'INFO', 'WARNING'])
        )
        general_result = await db.execute(general_stmt)
        general_deleted = general_result.rowcount

        # Delete error logs (ERROR, CRITICAL) older than error_retention_days
        error_stmt = delete(ApplicationLog).where(
            ApplicationLog.timestamp < error_cutoff,
            ApplicationLog.level.in_(['ERROR', 'CRITICAL'])
        )
        error_result = await db.execute(error_stmt)
        error_deleted = error_result.rowcount

        await db.commit()

        # Get remaining log count
        count_stmt = select(ApplicationLog)
        count_result = await db.execute(count_stmt)
        remaining_count = len(count_result.scalars().all())

        stats = {
            'general_deleted': general_deleted,
            'error_deleted': error_deleted,
            'total_deleted': general_deleted + error_deleted,
            'remaining_logs': remaining_count,
            'general_cutoff_date': general_cutoff.isoformat(),
            'error_cutoff_date': error_cutoff.isoformat(),
        }

        logger.info(
            f"Log cleanup completed: deleted {stats['total_deleted']} logs "
            f"(general={general_deleted}, errors={error_deleted}), "
            f"remaining={remaining_count}"
        )

        return stats

    except Exception as e:
        await db.rollback()
        logger.error(f"Log cleanup failed: {e}")
        raise
    finally:
        if close_session:
            await db.close()


async def cleanup_job_logs(db: AsyncSession = None, days: int = 90) -> dict:
    """
    Clean up old job logs.

    Args:
        db: Database session (optional)
        days: Number of days to keep job logs

    Returns:
        dict: Cleanup statistics
    """
    from backend.models.backup import JobLog

    close_session = False
    if db is None:
        db = AsyncSessionLocal()
        close_session = True

    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        logger.info(f"Starting job log cleanup: retention={days}d")

        # Delete old job logs
        stmt = delete(JobLog).where(JobLog.timestamp < cutoff_date)
        result = await db.execute(stmt)
        deleted_count = result.rowcount

        await db.commit()

        # Get remaining count
        count_stmt = select(JobLog)
        count_result = await db.execute(count_stmt)
        remaining_count = len(count_result.scalars().all())

        stats = {
            'deleted': deleted_count,
            'remaining': remaining_count,
            'cutoff_date': cutoff_date.isoformat(),
        }

        logger.info(f"Job log cleanup completed: deleted {deleted_count} logs, remaining={remaining_count}")

        return stats

    except Exception as e:
        await db.rollback()
        logger.error(f"Job log cleanup failed: {e}")
        raise
    finally:
        if close_session:
            await db.close()


async def run_log_cleanup() -> dict:
    """
    Run all log cleanup tasks.

    Returns:
        dict: Combined cleanup statistics
    """
    logger.info("Starting scheduled log cleanup")

    async with AsyncSessionLocal() as db:
        try:
            # Cleanup application logs
            app_log_stats = await cleanup_application_logs(db)

            # Cleanup job logs (using same retention as general logs)
            settings = await get_logging_settings(db)
            job_log_stats = await cleanup_job_logs(db, days=settings['logging.retention_days'])

            combined_stats = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'application_logs': app_log_stats,
                'job_logs': job_log_stats,
                'total_deleted': app_log_stats['total_deleted'] + job_log_stats['deleted'],
            }

            logger.info(f"Scheduled log cleanup completed: total deleted={combined_stats['total_deleted']}")

            return combined_stats

        except Exception as e:
            logger.error(f"Scheduled log cleanup failed: {e}")
            raise
