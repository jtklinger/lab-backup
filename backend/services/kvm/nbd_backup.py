"""
NBD-based backup export service for block-level incremental backups.

Uses QEMU's NBD (Network Block Device) server to export VM disks with
dirty bitmap filtering, enabling efficient incremental backups.

Requires QEMU 4.0+ for NBD dirty bitmap support.

Related: Issue #15 - Implement Changed Block Tracking (CBT)
"""

import logging
import socket
import json
import struct
import os
import hashlib
from typing import Optional, Dict, Any, List, Tuple, BinaryIO
from pathlib import Path
from datetime import datetime
import tempfile

logger = logging.getLogger(__name__)


class NBDExportError(Exception):
    """Exception raised for NBD export errors."""
    pass


class BlockRange:
    """Represents a range of blocks in a disk."""

    def __init__(self, offset: int, length: int):
        self.offset = offset
        self.length = length

    def __repr__(self) -> str:
        return f"BlockRange(offset={self.offset}, length={self.length})"


class NBDBackupMetadata:
    """Metadata for an NBD-based incremental backup."""

    def __init__(
        self,
        backup_id: Optional[int] = None,
        disk_target: str = "",
        bitmap_name: Optional[str] = None,
        block_size: int = 65536,
        disk_size: int = 0,
        changed_blocks: List[Tuple[int, int]] = None
    ):
        self.backup_id = backup_id
        self.disk_target = disk_target
        self.bitmap_name = bitmap_name
        self.block_size = block_size
        self.disk_size = disk_size
        self.changed_blocks = changed_blocks or []
        self.backup_timestamp = datetime.utcnow().isoformat()
        self.format_version = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "format_version": self.format_version,
            "backup_id": self.backup_id,
            "disk_target": self.disk_target,
            "bitmap_name": self.bitmap_name,
            "block_size": self.block_size,
            "disk_size": self.disk_size,
            "changed_blocks": self.changed_blocks,
            "backup_timestamp": self.backup_timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NBDBackupMetadata':
        """Create from dictionary."""
        return cls(
            backup_id=data.get("backup_id"),
            disk_target=data.get("disk_target", ""),
            bitmap_name=data.get("bitmap_name"),
            block_size=data.get("block_size", 65536),
            disk_size=data.get("disk_size", 0),
            changed_blocks=data.get("changed_blocks", [])
        )


class NBDBackupService:
    """
    Service for performing block-level backups via NBD.

    Workflow:
    1. Start NBD export with dirty bitmap filter
    2. Query dirty bitmap for changed block list
    3. Connect to NBD socket
    4. Read only changed blocks
    5. Write to backup file with metadata
    6. Calculate checksums
    """

    def __init__(self, domain, cbt_service):
        """
        Initialize NBD backup service.

        Args:
            domain: Libvirt domain object
            cbt_service: ChangedBlockTrackingService instance
        """
        self.domain = domain
        self.cbt_service = cbt_service
        self.nbd_socket_path: Optional[str] = None

    def start_nbd_export(
        self,
        disk_target: str,
        export_name: str = "backup",
        bitmap_name: Optional[str] = None
    ) -> str:
        """
        Start NBD export for a disk with optional dirty bitmap filter.

        Args:
            disk_target: Disk target device (e.g., 'vda')
            export_name: NBD export name
            bitmap_name: Optional dirty bitmap to filter blocks

        Returns:
            Unix socket path for NBD connection

        Raises:
            NBDExportError if export fails
        """
        # Create temporary Unix socket for NBD
        socket_dir = Path(tempfile.gettempdir()) / "lab-backup-nbd"
        socket_dir.mkdir(exist_ok=True)

        socket_path = str(socket_dir / f"nbd-{self.domain.name()}-{disk_target}-{int(datetime.utcnow().timestamp())}.sock")

        logger.info(
            f"Starting NBD export for {disk_target} "
            f"(bitmap: {bitmap_name or 'none'}) at {socket_path}"
        )

        try:
            # Build QMP command for NBD export
            command = {
                "execute": "nbd-server-start",
                "arguments": {
                    "addr": {
                        "type": "unix",
                        "data": {
                            "path": socket_path
                        }
                    }
                }
            }

            # Start NBD server
            self.cbt_service._execute_qmp_command(command)

            # Add disk to NBD export
            add_command = {
                "execute": "nbd-server-add",
                "arguments": {
                    "device": disk_target,
                    "name": export_name,
                    "writable": False
                }
            }

            # If bitmap specified, add bitmap filter
            if bitmap_name:
                add_command["arguments"]["bitmap"] = bitmap_name

            self.cbt_service._execute_qmp_command(add_command)

            self.nbd_socket_path = socket_path
            logger.info(f"NBD export started successfully at {socket_path}")

            return socket_path

        except Exception as e:
            logger.error(f"Failed to start NBD export: {e}")
            raise NBDExportError(f"Failed to start NBD export: {e}")

    def stop_nbd_export(self, export_name: str = "backup") -> None:
        """
        Stop NBD export and clean up.

        Args:
            export_name: NBD export name to remove
        """
        try:
            # Remove NBD export
            command = {
                "execute": "nbd-server-remove",
                "arguments": {
                    "name": export_name
                }
            }
            self.cbt_service._execute_qmp_command(command)

            # Stop NBD server
            stop_command = {
                "execute": "nbd-server-stop",
                "arguments": {}
            }
            self.cbt_service._execute_qmp_command(stop_command)

            # Clean up socket file
            if self.nbd_socket_path and os.path.exists(self.nbd_socket_path):
                os.unlink(self.nbd_socket_path)

            logger.info("NBD export stopped successfully")

        except Exception as e:
            logger.warning(f"Error stopping NBD export: {e}")

    def export_full_backup(
        self,
        disk_target: str,
        output_path: str,
        block_size: int = 65536
    ) -> Dict[str, Any]:
        """
        Export full backup of a disk.

        Args:
            disk_target: Disk target device
            output_path: Path to write backup file
            block_size: Block size for reading (default 64KB)

        Returns:
            Dictionary with backup statistics
        """
        logger.info(f"Starting full backup of {disk_target} to {output_path}")

        try:
            # Start NBD export without bitmap (full disk)
            socket_path = self.start_nbd_export(disk_target, export_name="backup")

            # Get disk size via QMP
            disk_info = self._get_disk_info(disk_target)
            disk_size = disk_info.get("size", 0)

            logger.info(f"Disk size: {disk_size} bytes ({disk_size / (1024**3):.2f} GB)")

            # Create metadata
            metadata = NBDBackupMetadata(
                disk_target=disk_target,
                bitmap_name=None,
                block_size=block_size,
                disk_size=disk_size,
                changed_blocks=[(0, disk_size)]  # Full disk
            )

            # Read full disk via NBD and write to backup file
            stats = self._read_and_write_blocks(
                socket_path,
                output_path,
                metadata
            )

            return stats

        finally:
            self.stop_nbd_export()

    def export_incremental_backup(
        self,
        disk_target: str,
        bitmap_name: str,
        output_path: str,
        block_size: int = 65536
    ) -> Dict[str, Any]:
        """
        Export incremental backup using dirty bitmap.

        Args:
            disk_target: Disk target device
            bitmap_name: Dirty bitmap name
            output_path: Path to write backup file
            block_size: Block size for reading

        Returns:
            Dictionary with backup statistics
        """
        logger.info(
            f"Starting incremental backup of {disk_target} "
            f"using bitmap {bitmap_name} to {output_path}"
        )

        try:
            # Query bitmap information
            bitmap_info = self.cbt_service.query_bitmap(disk_target, bitmap_name)
            granularity = bitmap_info["granularity"]
            dirty_count = bitmap_info["count"]

            logger.info(
                f"Bitmap info: {dirty_count} dirty blocks, "
                f"granularity: {granularity} bytes"
            )

            # Get changed block ranges
            changed_blocks = self.cbt_service.get_changed_blocks(disk_target, bitmap_name)

            if not changed_blocks:
                logger.info("No changed blocks detected, skipping backup")
                return {
                    "original_size": 0,
                    "compressed_size": 0,
                    "changed_blocks_count": 0,
                    "block_size": granularity
                }

            # Start NBD export with bitmap filter
            socket_path = self.start_nbd_export(
                disk_target,
                export_name="backup",
                bitmap_name=bitmap_name
            )

            # Get disk size
            disk_info = self._get_disk_info(disk_target)
            disk_size = disk_info.get("size", 0)

            # Create metadata
            metadata = NBDBackupMetadata(
                disk_target=disk_target,
                bitmap_name=bitmap_name,
                block_size=granularity,
                disk_size=disk_size,
                changed_blocks=changed_blocks
            )

            # Read changed blocks via NBD and write to backup file
            stats = self._read_and_write_blocks(
                socket_path,
                output_path,
                metadata
            )

            # Clear bitmap after successful backup
            self.cbt_service.clear_bitmap(disk_target, bitmap_name)

            return stats

        finally:
            self.stop_nbd_export()

    def _get_disk_info(self, disk_target: str) -> Dict[str, Any]:
        """
        Get disk information via QMP.

        Args:
            disk_target: Disk target device

        Returns:
            Dictionary with disk information
        """
        command = {
            "execute": "query-block",
            "arguments": {}
        }

        response = self.cbt_service._execute_qmp_command(command)

        for device in response.get("return", []):
            if device.get("device") == disk_target or device.get("qdev") == disk_target:
                inserted = device.get("inserted", {})
                return {
                    "size": inserted.get("image", {}).get("virtual-size", 0),
                    "format": inserted.get("image", {}).get("format", "unknown")
                }

        raise NBDExportError(f"Disk {disk_target} not found")

    def _read_and_write_blocks(
        self,
        socket_path: str,
        output_path: str,
        metadata: NBDBackupMetadata
    ) -> Dict[str, Any]:
        """
        Read blocks via NBD and write to backup file.

        Args:
            socket_path: NBD Unix socket path
            output_path: Output backup file path
            metadata: Backup metadata

        Returns:
            Statistics dictionary
        """
        # For now, this is a simplified implementation
        # In production, we would:
        # 1. Connect to NBD socket
        # 2. Negotiate NBD protocol
        # 3. Read blocks according to changed_blocks list
        # 4. Write to output file with compression
        # 5. Calculate checksums

        # Placeholder implementation
        logger.warning(
            "NBD block reading not fully implemented yet. "
            "This is a placeholder that will be completed in next iteration."
        )

        # Write metadata file
        metadata_path = f"{output_path}.meta.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata.to_dict(), f, indent=2)

        logger.info(f"Wrote metadata to {metadata_path}")

        # Calculate total bytes to backup
        total_bytes = sum(length for _, length in metadata.changed_blocks)

        return {
            "original_size": total_bytes,
            "compressed_size": total_bytes,  # No compression yet
            "changed_blocks_count": len(metadata.changed_blocks),
            "block_size": metadata.block_size,
            "checksum": "placeholder"
        }
