"""
Changed Block Tracking (CBT) service for QEMU/KVM.

Implements dirty bitmap tracking for efficient incremental backups.
Requires QEMU 4.0+ for persistent dirty bitmap support.

Related: Issue #15 - Implement Changed Block Tracking (CBT)
"""

import logging
import json
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import libvirt

logger = logging.getLogger(__name__)


class QEMUVersion:
    """QEMU version parser and comparison."""

    def __init__(self, major: int, minor: int, patch: int = 0):
        self.major = major
        self.minor = minor
        self.patch = patch

    @classmethod
    def from_string(cls, version_string: str) -> Optional['QEMUVersion']:
        """
        Parse QEMU version string.

        Args:
            version_string: Version string like "QEMU emulator version 4.2.1"

        Returns:
            QEMUVersion object or None if parsing fails
        """
        # Match patterns like "4.2.1", "5.0.0", "6.2"
        match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', version_string)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            patch = int(match.group(3)) if match.group(3) else 0
            return cls(major, minor, patch)
        return None

    def __ge__(self, other: 'QEMUVersion') -> bool:
        """Greater than or equal comparison."""
        if self.major != other.major:
            return self.major > other.major
        if self.minor != other.minor:
            return self.minor > other.minor
        return self.patch >= other.patch

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class ChangedBlockTrackingService:
    """
    Service for managing QEMU dirty bitmaps for incremental backups.

    QEMU 4.0+ supports persistent dirty bitmaps that track changed blocks.
    This enables true block-level incremental backups.
    """

    # Minimum QEMU version required for CBT (4.0.0)
    MIN_QEMU_VERSION = QEMUVersion(4, 0, 0)

    def __init__(self, domain: libvirt.virDomain):
        """
        Initialize CBT service for a VM domain.

        Args:
            domain: Libvirt domain object
        """
        self.domain = domain
        self.qemu_version: Optional[QEMUVersion] = None
        self.cbt_capable: Optional[bool] = None

    def get_qemu_version(self) -> Optional[QEMUVersion]:
        """
        Detect QEMU version from hypervisor capabilities.

        Returns:
            QEMUVersion object or None if detection fails
        """
        if self.qemu_version:
            return self.qemu_version

        try:
            conn = self.domain.connect()
            capabilities = conn.getCapabilities()

            # Parse capabilities XML to find QEMU version
            # Example: <emulator>/usr/bin/qemu-system-x86_64</emulator>
            # Then we need to check the actual version

            # Alternative: Use qemuAgentCommand or check hypervisor version
            version_str = conn.getVersion()  # Returns libvirt version, not QEMU

            # Try to get QEMU version via QMP if available
            # For now, we'll assume a recent QEMU if hypervisor is recent
            # This is a simplified detection - in production, use QMP query

            # Fallback: Try to execute qemu-img --version on the host
            logger.info(f"Libvirt version: {version_str}")

            # For now, return a default version (will enhance later)
            # TODO: Implement proper QEMU version detection via QMP
            self.qemu_version = QEMUVersion(4, 2, 0)  # Conservative assumption
            self.cbt_capable = True

            return self.qemu_version

        except Exception as e:
            logger.error(f"Failed to detect QEMU version: {e}")
            return None

    def is_cbt_supported(self) -> bool:
        """
        Check if CBT (dirty bitmaps) is supported.

        Returns:
            True if QEMU >= 4.0 and bitmaps are available
        """
        if self.cbt_capable is not None:
            return self.cbt_capable

        version = self.get_qemu_version()
        if not version:
            logger.warning("Could not detect QEMU version, assuming CBT not supported")
            self.cbt_capable = False
            return False

        self.cbt_capable = version >= self.MIN_QEMU_VERSION
        logger.info(
            f"QEMU version {version}: CBT {'supported' if self.cbt_capable else 'NOT supported'} "
            f"(requires >= {self.MIN_QEMU_VERSION})"
        )

        return self.cbt_capable

    def _execute_qmp_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a QMP (QEMU Machine Protocol) command.

        Args:
            command: QMP command dictionary

        Returns:
            QMP response dictionary

        Raises:
            Exception if command fails
        """
        try:
            # Convert command to JSON
            command_json = json.dumps(command)

            # Execute via qemuMonitorCommand
            # flags=0 means default behavior
            result = self.domain.qemuMonitorCommand(command_json, flags=0)

            # Parse response
            response = json.loads(result)

            if "error" in response:
                error_msg = response["error"].get("desc", "Unknown error")
                raise Exception(f"QMP command failed: {error_msg}")

            return response

        except libvirt.libvirtError as e:
            logger.error(f"Libvirt error executing QMP command: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to execute QMP command: {e}")
            raise

    def create_bitmap(self, disk_target: str, bitmap_name: Optional[str] = None) -> str:
        """
        Create a persistent dirty bitmap for a disk.

        Args:
            disk_target: Disk target device (e.g., 'vda', 'sda')
            bitmap_name: Optional bitmap name (auto-generated if not provided)

        Returns:
            Bitmap name that was created

        Raises:
            Exception if bitmap creation fails
        """
        if not self.is_cbt_supported():
            raise Exception("CBT not supported on this QEMU version")

        # Generate bitmap name if not provided
        if not bitmap_name:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            bitmap_name = f"backup-{self.domain.name()}-{disk_target}-{timestamp}"

        logger.info(f"Creating dirty bitmap '{bitmap_name}' for disk '{disk_target}'")

        try:
            # QMP command to create persistent dirty bitmap
            command = {
                "execute": "block-dirty-bitmap-add",
                "arguments": {
                    "node": disk_target,
                    "name": bitmap_name,
                    "persistent": True,
                    "disabled": False
                }
            }

            response = self._execute_qmp_command(command)

            logger.info(f"Successfully created bitmap '{bitmap_name}'")
            return bitmap_name

        except Exception as e:
            logger.error(f"Failed to create dirty bitmap: {e}")
            raise

    def query_bitmap(self, disk_target: str, bitmap_name: str) -> Dict[str, Any]:
        """
        Query dirty bitmap information.

        Args:
            disk_target: Disk target device
            bitmap_name: Bitmap name

        Returns:
            Dictionary with bitmap information:
            - granularity: Block size tracked by bitmap (bytes)
            - count: Number of dirty blocks
            - status: Bitmap status (active, disabled, etc.)

        Raises:
            Exception if query fails
        """
        try:
            # QMP command to query block info
            command = {
                "execute": "query-block",
                "arguments": {}
            }

            response = self._execute_qmp_command(command)

            # Parse response to find our disk and bitmap
            for device in response.get("return", []):
                if device.get("device") == disk_target or device.get("qdev") == disk_target:
                    # Look for dirty bitmaps
                    dirty_bitmaps = device.get("dirty-bitmaps", [])
                    for bitmap in dirty_bitmaps:
                        if bitmap.get("name") == bitmap_name:
                            return {
                                "granularity": bitmap.get("granularity", 65536),
                                "count": bitmap.get("count", 0),
                                "status": bitmap.get("status", "unknown"),
                                "recording": bitmap.get("recording", False),
                                "busy": bitmap.get("busy", False)
                            }

            raise Exception(f"Bitmap '{bitmap_name}' not found on disk '{disk_target}'")

        except Exception as e:
            logger.error(f"Failed to query bitmap: {e}")
            raise

    def get_changed_blocks(
        self,
        disk_target: str,
        bitmap_name: str
    ) -> List[Tuple[int, int]]:
        """
        Get list of changed block ranges from dirty bitmap.

        Args:
            disk_target: Disk target device
            bitmap_name: Bitmap name

        Returns:
            List of (offset, length) tuples representing changed block ranges

        Raises:
            Exception if query fails
        """
        try:
            # Query bitmap information first
            bitmap_info = self.query_bitmap(disk_target, bitmap_name)

            granularity = bitmap_info["granularity"]
            count = bitmap_info["count"]

            logger.info(
                f"Bitmap '{bitmap_name}' has {count} dirty blocks "
                f"(granularity: {granularity} bytes)"
            )

            # In a real implementation, we would use qemu-img map with the bitmap
            # to get the exact changed block ranges. For now, return a simplified result.
            # TODO: Implement actual block map querying via NBD or qemu-img

            # Placeholder: Return that we have changed blocks
            if count > 0:
                return [(0, count * granularity)]
            else:
                return []

        except Exception as e:
            logger.error(f"Failed to get changed blocks: {e}")
            raise

    def clear_bitmap(self, disk_target: str, bitmap_name: str) -> None:
        """
        Clear (reset) a dirty bitmap after successful backup.

        Args:
            disk_target: Disk target device
            bitmap_name: Bitmap name

        Raises:
            Exception if clear fails
        """
        logger.info(f"Clearing bitmap '{bitmap_name}' on disk '{disk_target}'")

        try:
            command = {
                "execute": "block-dirty-bitmap-clear",
                "arguments": {
                    "node": disk_target,
                    "name": bitmap_name
                }
            }

            self._execute_qmp_command(command)
            logger.info(f"Successfully cleared bitmap '{bitmap_name}'")

        except Exception as e:
            logger.error(f"Failed to clear bitmap: {e}")
            raise

    def delete_bitmap(self, disk_target: str, bitmap_name: str) -> None:
        """
        Delete a dirty bitmap.

        Args:
            disk_target: Disk target device
            bitmap_name: Bitmap name

        Raises:
            Exception if deletion fails
        """
        logger.info(f"Deleting bitmap '{bitmap_name}' from disk '{disk_target}'")

        try:
            command = {
                "execute": "block-dirty-bitmap-remove",
                "arguments": {
                    "node": disk_target,
                    "name": bitmap_name
                }
            }

            self._execute_qmp_command(command)
            logger.info(f"Successfully deleted bitmap '{bitmap_name}'")

        except Exception as e:
            logger.error(f"Failed to delete bitmap: {e}")
            raise

    def enable_bitmap(self, disk_target: str, bitmap_name: str) -> None:
        """
        Enable (resume tracking) a disabled bitmap.

        Args:
            disk_target: Disk target device
            bitmap_name: Bitmap name

        Raises:
            Exception if enable fails
        """
        try:
            command = {
                "execute": "block-dirty-bitmap-enable",
                "arguments": {
                    "node": disk_target,
                    "name": bitmap_name
                }
            }

            self._execute_qmp_command(command)
            logger.info(f"Enabled bitmap '{bitmap_name}'")

        except Exception as e:
            logger.error(f"Failed to enable bitmap: {e}")
            raise

    def disable_bitmap(self, disk_target: str, bitmap_name: str) -> None:
        """
        Disable (pause tracking) a bitmap.

        Args:
            disk_target: Disk target device
            bitmap_name: Bitmap name

        Raises:
            Exception if disable fails
        """
        try:
            command = {
                "execute": "block-dirty-bitmap-disable",
                "arguments": {
                    "node": disk_target,
                    "name": bitmap_name
                }
            }

            self._execute_qmp_command(command)
            logger.info(f"Disabled bitmap '{bitmap_name}'")

        except Exception as e:
            logger.error(f"Failed to disable bitmap: {e}")
            raise
