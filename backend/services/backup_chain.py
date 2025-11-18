"""
Backup chain management service.

Handles backup chain tracking, deduplication/compression metrics,
and orphaned backup detection.

Related: Issue #10 - Implement Backup Chain Tracking and Metadata
"""

import logging
import uuid
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.backup import Backup, BackupMode, BackupStatus, SourceType

logger = logging.getLogger(__name__)


class BackupChainService:
    """Service for managing backup chains and calculating storage metrics."""

    def __init__(self, db: AsyncSession):
        """
        Initialize backup chain service.

        Args:
            db: Database session
        """
        self.db = db

    async def get_last_backup(
        self,
        source_type: SourceType,
        source_id: int,
        status: BackupStatus = BackupStatus.COMPLETED
    ) -> Optional[Backup]:
        """
        Get the most recent completed backup for a source.

        Args:
            source_type: VM or CONTAINER
            source_id: Source ID
            status: Backup status to filter by (default: COMPLETED)

        Returns:
            Most recent backup or None
        """
        stmt = (
            select(Backup)
            .where(
                and_(
                    Backup.source_type == source_type,
                    Backup.source_id == source_id,
                    Backup.status == status
                )
            )
            .order_by(desc(Backup.completed_at))
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def initialize_backup_chain(
        self,
        backup: Backup,
        backup_mode: BackupMode,
        original_size: Optional[int] = None,
        deduplicated_size: Optional[int] = None
    ) -> None:
        """
        Initialize backup chain metadata for a new backup.

        For full backups: Creates new chain_id, sets sequence_number=0
        For incremental backups: Reuses chain_id from parent, increments sequence

        Args:
            backup: Backup record being created
            backup_mode: FULL or INCREMENTAL
            original_size: Size before deduplication (bytes)
            deduplicated_size: Size after dedup but before compression (bytes)
        """
        last_backup = await self.get_last_backup(
            backup.source_type,
            backup.source_id
        )

        if backup_mode == BackupMode.FULL or not last_backup:
            # Full backup or first backup ever - start new chain
            backup.chain_id = str(uuid.uuid4())
            backup.parent_backup_id = None
            backup.sequence_number = 0
            logger.info(
                f"Started new backup chain {backup.chain_id} for "
                f"{backup.source_type.value} {backup.source_name}"
            )
        else:
            # Incremental backup - continue existing chain
            backup.chain_id = last_backup.chain_id
            backup.parent_backup_id = last_backup.id
            backup.sequence_number = (last_backup.sequence_number or 0) + 1
            logger.info(
                f"Continuing backup chain {backup.chain_id} "
                f"(sequence {backup.sequence_number}) for "
                f"{backup.source_type.value} {backup.source_name}"
            )

        # Calculate and store metrics
        self.calculate_metrics(
            backup,
            original_size=original_size,
            deduplicated_size=deduplicated_size
        )

    def calculate_metrics(
        self,
        backup: Backup,
        original_size: Optional[int] = None,
        deduplicated_size: Optional[int] = None
    ) -> None:
        """
        Calculate deduplication and compression ratios.

        Ratios:
        - dedupe_ratio = original_size / deduplicated_size (higher is better)
        - compression_ratio = deduplicated_size / compressed_size (higher is better)
        - space_saved_bytes = original_size - compressed_size

        Args:
            backup: Backup record to update
            original_size: Size before deduplication (bytes)
            deduplicated_size: Size after dedup but before compression (bytes)
        """
        # For now, if we don't have actual dedup data, use size as original_size
        # and compressed_size as the deduplicated size
        if original_size is None:
            original_size = backup.size or backup.compressed_size

        if deduplicated_size is None:
            deduplicated_size = backup.compressed_size

        backup.original_size = original_size

        # Calculate deduplication ratio
        if original_size and deduplicated_size and deduplicated_size > 0:
            backup.dedupe_ratio = round(original_size / deduplicated_size, 2)
        else:
            backup.dedupe_ratio = 1.0  # No deduplication

        # Calculate compression ratio
        if deduplicated_size and backup.compressed_size and backup.compressed_size > 0:
            backup.compression_ratio = round(deduplicated_size / backup.compressed_size, 2)
        else:
            backup.compression_ratio = 1.0  # No compression

        # Calculate total space saved
        if original_size and backup.compressed_size:
            backup.space_saved_bytes = original_size - backup.compressed_size
        else:
            backup.space_saved_bytes = 0

        logger.debug(
            f"Backup {backup.id} metrics: "
            f"dedupe_ratio={backup.dedupe_ratio:.2f}x, "
            f"compression_ratio={backup.compression_ratio:.2f}x, "
            f"space_saved={backup.space_saved_bytes / (1024**3):.2f} GB"
        )

    async def get_backup_chain(
        self,
        chain_id: str,
        include_failed: bool = False
    ) -> List[Backup]:
        """
        Get all backups in a chain, ordered by sequence number.

        Args:
            chain_id: Chain UUID
            include_failed: Include failed backups in results

        Returns:
            List of backups in chain order
        """
        conditions = [Backup.chain_id == chain_id]

        if not include_failed:
            conditions.append(Backup.status == BackupStatus.COMPLETED)

        stmt = (
            select(Backup)
            .where(and_(*conditions))
            .order_by(Backup.sequence_number)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_orphaned_backups(self) -> List[Backup]:
        """
        Find backups whose parent was deleted.

        Returns:
            List of orphaned backups (parent_backup_id points to non-existent backup)
        """
        # Subquery to find all valid backup IDs
        valid_ids_subq = select(Backup.id).subquery()

        # Find backups with parent_backup_id not in valid IDs
        stmt = select(Backup).where(
            and_(
                Backup.parent_backup_id.isnot(None),
                Backup.parent_backup_id.notin_(select(valid_ids_subq))
            )
        )

        result = await self.db.execute(stmt)
        orphaned = list(result.scalars().all())

        if orphaned:
            logger.warning(f"Found {len(orphaned)} orphaned backups")

        return orphaned

    async def get_backup_children(self, backup_id: int) -> List[Backup]:
        """
        Get all child backups (incrementals) that depend on this backup.

        Args:
            backup_id: Parent backup ID

        Returns:
            List of child backups
        """
        stmt = select(Backup).where(Backup.parent_backup_id == backup_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def can_delete_backup(self, backup_id: int) -> Tuple[bool, Optional[str]]:
        """
        Check if a backup can be safely deleted.

        A backup cannot be deleted if it has dependent incremental backups.

        Args:
            backup_id: Backup to check

        Returns:
            Tuple of (can_delete, reason_if_not)
        """
        children = await self.get_backup_children(backup_id)

        if children:
            child_ids = [str(c.id) for c in children]
            return (
                False,
                f"Cannot delete backup {backup_id}: "
                f"has {len(children)} dependent backup(s): {', '.join(child_ids)}"
            )

        return (True, None)

    async def get_chain_statistics(self, chain_id: str) -> Dict[str, Any]:
        """
        Get statistics for a backup chain.

        Args:
            chain_id: Chain UUID

        Returns:
            Dictionary with chain statistics
        """
        backups = await self.get_backup_chain(chain_id)

        if not backups:
            return {
                "chain_id": chain_id,
                "backup_count": 0,
                "error": "Chain not found"
            }

        total_original = sum(b.original_size or 0 for b in backups)
        total_compressed = sum(b.compressed_size or 0 for b in backups)
        total_saved = sum(b.space_saved_bytes or 0 for b in backups)

        avg_dedupe = sum(b.dedupe_ratio or 1.0 for b in backups) / len(backups)
        avg_compression = sum(b.compression_ratio or 1.0 for b in backups) / len(backups)

        return {
            "chain_id": chain_id,
            "source_type": backups[0].source_type.value,
            "source_id": backups[0].source_id,
            "source_name": backups[0].source_name,
            "backup_count": len(backups),
            "first_backup": backups[0].created_at.isoformat(),
            "last_backup": backups[-1].created_at.isoformat(),
            "total_original_size_bytes": total_original,
            "total_compressed_size_bytes": total_compressed,
            "total_space_saved_bytes": total_saved,
            "average_dedupe_ratio": round(avg_dedupe, 2),
            "average_compression_ratio": round(avg_compression, 2),
            "backups": [
                {
                    "id": b.id,
                    "sequence": b.sequence_number,
                    "mode": b.backup_mode.value,
                    "created_at": b.created_at.isoformat(),
                    "size": b.compressed_size,
                    "dedupe_ratio": b.dedupe_ratio,
                    "compression_ratio": b.compression_ratio
                }
                for b in backups
            ]
        }

    async def get_global_statistics(self) -> Dict[str, Any]:
        """
        Get global backup storage statistics across all chains.

        Returns:
            Dictionary with global statistics
        """
        # Get all completed backups
        stmt = select(Backup).where(Backup.status == BackupStatus.COMPLETED)
        result = await self.db.execute(stmt)
        backups = list(result.scalars().all())

        if not backups:
            return {
                "total_backups": 0,
                "total_chains": 0,
                "message": "No backups found"
            }

        total_original = sum(b.original_size or 0 for b in backups)
        total_compressed = sum(b.compressed_size or 0 for b in backups)
        total_saved = sum(b.space_saved_bytes or 0 for b in backups)

        # Count unique chains
        unique_chains = len(set(b.chain_id for b in backups if b.chain_id))

        # Calculate averages (only for backups with metrics)
        backups_with_dedupe = [b for b in backups if b.dedupe_ratio]
        backups_with_compression = [b for b in backups if b.compression_ratio]

        avg_dedupe = (
            sum(b.dedupe_ratio for b in backups_with_dedupe) / len(backups_with_dedupe)
            if backups_with_dedupe else 1.0
        )

        avg_compression = (
            sum(b.compression_ratio for b in backups_with_compression) / len(backups_with_compression)
            if backups_with_compression else 1.0
        )

        return {
            "total_backups": len(backups),
            "total_chains": unique_chains,
            "total_original_size_bytes": total_original,
            "total_original_size_gb": round(total_original / (1024**3), 2),
            "total_compressed_size_bytes": total_compressed,
            "total_compressed_size_gb": round(total_compressed / (1024**3), 2),
            "total_space_saved_bytes": total_saved,
            "total_space_saved_gb": round(total_saved / (1024**3), 2),
            "average_dedupe_ratio": round(avg_dedupe, 2),
            "average_compression_ratio": round(avg_compression, 2),
            "overall_efficiency": round(
                (total_saved / total_original * 100) if total_original > 0 else 0,
                2
            )
        }
