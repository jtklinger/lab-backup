"""
Libvirt Checkpoint Service for incremental backups.

Uses libvirt's checkpoint API (libvirt 6.0+) for managing dirty bitmaps
in a way that's integrated with the backup workflow. This is the preferred
approach over direct QMP commands for live VM backups.

Related: Issue #15 - Implement Changed Block Tracking (CBT)
"""

import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List
from datetime import datetime
import libvirt

logger = logging.getLogger(__name__)


class CheckpointError(Exception):
    """Exception raised for checkpoint operations."""
    pass


class IncrementalNotSupportedError(CheckpointError):
    """Exception raised when incremental backup is not supported."""
    pass


class CheckpointService:
    """
    Service for managing libvirt checkpoints for incremental backups.

    Libvirt checkpoints provide a higher-level abstraction over QEMU dirty
    bitmaps, integrating with the backup workflow for consistent incremental
    backups of live VMs.

    Requirements:
    - libvirt >= 6.0
    - QEMU >= 4.2
    - Domain must be running or have persistent bitmaps
    """

    # Minimum versions required
    MIN_LIBVIRT_VERSION = 6000000  # 6.0.0
    MIN_QEMU_VERSION = (4, 2)

    def __init__(self, log_callback=None):
        """
        Initialize checkpoint service.

        Args:
            log_callback: Optional callback for logging (level, message, details)
        """
        self.log_callback = log_callback

    def _log(self, level: str, message: str, details: dict = None):
        """Log message via callback and standard logger."""
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(message)
        if self.log_callback:
            self.log_callback(level, message, details)

    def check_checkpoint_support(self, conn: libvirt.virConnect, domain: libvirt.virDomain) -> Dict[str, Any]:
        """
        Check if hypervisor and domain support checkpoints.

        Args:
            conn: Libvirt connection
            domain: Libvirt domain

        Returns:
            Dictionary with support status and details:
            - supported: bool
            - libvirt_version: int
            - qemu_version: tuple or None
            - checkpoint_capable: bool
            - reason: str or None (if not supported)
        """
        result = {
            "supported": False,
            "libvirt_version": 0,
            "qemu_version": None,
            "checkpoint_capable": False,
            "reason": None
        }

        try:
            # Check libvirt version
            libvirt_version = conn.getLibVersion()
            result["libvirt_version"] = libvirt_version

            if libvirt_version < self.MIN_LIBVIRT_VERSION:
                result["reason"] = (
                    f"libvirt version {libvirt_version} < {self.MIN_LIBVIRT_VERSION} required"
                )
                return result

            # Try to get QEMU version from hypervisor capabilities
            qemu_version = self._get_qemu_version(conn)
            result["qemu_version"] = qemu_version

            if qemu_version and qemu_version < self.MIN_QEMU_VERSION:
                result["reason"] = (
                    f"QEMU version {qemu_version} < {self.MIN_QEMU_VERSION} required"
                )
                return result

            # Check if domain supports checkpoints by trying to list them
            try:
                domain.listAllCheckpoints()
                result["checkpoint_capable"] = True
            except libvirt.libvirtError as e:
                # Error code 84 = VIR_ERR_NO_SUPPORT
                if e.get_error_code() == libvirt.VIR_ERR_NO_SUPPORT:
                    result["reason"] = "Domain does not support checkpoints"
                    return result
                # Other errors might be OK (e.g., empty list)
                result["checkpoint_capable"] = True

            result["supported"] = True
            self._log("INFO", f"Checkpoint support verified for domain {domain.name()}", {
                "libvirt_version": libvirt_version,
                "qemu_version": str(qemu_version) if qemu_version else "unknown",
            })

            return result

        except Exception as e:
            result["reason"] = str(e)
            logger.error(f"Error checking checkpoint support: {e}")
            return result

    def _get_qemu_version(self, conn: libvirt.virConnect) -> Optional[tuple]:
        """
        Get QEMU version from hypervisor.

        Args:
            conn: Libvirt connection

        Returns:
            Tuple of (major, minor, patch) or None
        """
        try:
            # Get hypervisor version - returns packed version number
            # Format: major * 1000000 + minor * 1000 + release
            hv_version = conn.getVersion()
            if hv_version:
                major = hv_version // 1000000
                minor = (hv_version % 1000000) // 1000
                patch = hv_version % 1000
                return (major, minor, patch)
        except libvirt.libvirtError:
            pass

        return None

    def create_checkpoint(
        self,
        domain: libvirt.virDomain,
        checkpoint_name: str,
        disk_targets: List[str],
        description: str = None
    ) -> str:
        """
        Create a checkpoint for tracking changes after backup.

        Args:
            domain: Libvirt domain
            checkpoint_name: Name for the checkpoint
            disk_targets: List of disk targets to track (e.g., ['vda', 'vdb'])
            description: Optional description

        Returns:
            Checkpoint name that was created

        Raises:
            CheckpointError: If creation fails
        """
        self._log("INFO", f"Creating checkpoint '{checkpoint_name}' for domain {domain.name()}", {
            "disk_targets": disk_targets
        })

        try:
            # Build checkpoint XML
            checkpoint_xml = self._build_checkpoint_xml(
                checkpoint_name,
                disk_targets,
                description
            )

            self._log("DEBUG", "Checkpoint XML", {"xml": checkpoint_xml})

            # Create checkpoint
            # Flag 0 = default behavior
            checkpoint = domain.checkpointCreateXML(checkpoint_xml, 0)

            self._log("INFO", f"Successfully created checkpoint '{checkpoint_name}'")
            return checkpoint_name

        except libvirt.libvirtError as e:
            error_msg = f"Failed to create checkpoint: {e}"
            self._log("ERROR", error_msg)
            raise CheckpointError(error_msg)

    def _build_checkpoint_xml(
        self,
        name: str,
        disk_targets: List[str],
        description: str = None
    ) -> str:
        """
        Build checkpoint XML for libvirt.

        Args:
            name: Checkpoint name
            disk_targets: List of disk targets
            description: Optional description

        Returns:
            Checkpoint XML string
        """
        root = ET.Element("domaincheckpoint")

        name_elem = ET.SubElement(root, "name")
        name_elem.text = name

        if description:
            desc_elem = ET.SubElement(root, "description")
            desc_elem.text = description

        disks_elem = ET.SubElement(root, "disks")
        for target in disk_targets:
            disk_elem = ET.SubElement(disks_elem, "disk")
            disk_elem.set("name", target)
            disk_elem.set("checkpoint", "bitmap")

        return ET.tostring(root, encoding="unicode")

    def get_checkpoint(
        self,
        domain: libvirt.virDomain,
        checkpoint_name: str
    ) -> Optional[libvirt.virDomainCheckpoint]:
        """
        Get existing checkpoint by name.

        Args:
            domain: Libvirt domain
            checkpoint_name: Checkpoint name

        Returns:
            Checkpoint object or None if not found
        """
        try:
            return domain.checkpointLookupByName(checkpoint_name, 0)
        except libvirt.libvirtError:
            return None

    def list_checkpoints(self, domain: libvirt.virDomain) -> List[str]:
        """
        List all checkpoints for a domain.

        Args:
            domain: Libvirt domain

        Returns:
            List of checkpoint names
        """
        try:
            checkpoints = domain.listAllCheckpoints(0)
            return [cp.getName() for cp in checkpoints]
        except libvirt.libvirtError as e:
            logger.warning(f"Failed to list checkpoints: {e}")
            return []

    def delete_checkpoint(
        self,
        domain: libvirt.virDomain,
        checkpoint_name: str
    ) -> bool:
        """
        Delete a checkpoint.

        Args:
            domain: Libvirt domain
            checkpoint_name: Checkpoint name to delete

        Returns:
            True if deleted, False if not found
        """
        self._log("INFO", f"Deleting checkpoint '{checkpoint_name}'")

        try:
            checkpoint = domain.checkpointLookupByName(checkpoint_name, 0)
            checkpoint.delete(0)
            self._log("INFO", f"Successfully deleted checkpoint '{checkpoint_name}'")
            return True
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN_CHECKPOINT:
                self._log("WARNING", f"Checkpoint '{checkpoint_name}' not found")
                return False
            raise CheckpointError(f"Failed to delete checkpoint: {e}")

    def get_checkpoint_xml(
        self,
        domain: libvirt.virDomain,
        checkpoint_name: str
    ) -> Optional[str]:
        """
        Get checkpoint XML.

        Args:
            domain: Libvirt domain
            checkpoint_name: Checkpoint name

        Returns:
            Checkpoint XML string or None
        """
        try:
            checkpoint = domain.checkpointLookupByName(checkpoint_name, 0)
            return checkpoint.getXMLDesc(0)
        except libvirt.libvirtError:
            return None

    def start_backup(
        self,
        domain: libvirt.virDomain,
        disk_targets: List[str],
        scratch_dir: str,
        checkpoint_name: Optional[str] = None,
        incremental_from: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start a pull-mode backup using libvirt backup API.

        This creates NBD exports for the specified disks that can be
        accessed to read backup data.

        Args:
            domain: Libvirt domain
            disk_targets: List of disk targets to back up
            scratch_dir: Directory for scratch files
            checkpoint_name: Name for new checkpoint (created after backup)
            incremental_from: Previous checkpoint name for incremental backup

        Returns:
            Dictionary with NBD connection info for each disk:
            {
                "vda": {"socket": "/path/to/socket", "export_name": "vda"},
                ...
            }

        Raises:
            CheckpointError: If backup start fails
        """
        self._log("INFO", f"Starting backup for domain {domain.name()}", {
            "disk_targets": disk_targets,
            "incremental_from": incremental_from,
            "checkpoint_name": checkpoint_name
        })

        try:
            # Build backup XML
            backup_xml = self._build_backup_xml(
                disk_targets,
                scratch_dir,
                incremental_from
            )

            # Build checkpoint XML if creating new checkpoint
            checkpoint_xml = None
            if checkpoint_name:
                checkpoint_xml = self._build_checkpoint_xml(
                    checkpoint_name,
                    disk_targets,
                    f"Backup checkpoint created at {datetime.utcnow().isoformat()}"
                )

            self._log("DEBUG", "Backup XML", {"xml": backup_xml})

            # Start backup
            # VIR_DOMAIN_BACKUP_BEGIN_REUSE_EXTERNAL = 1 (reuse scratch files)
            flags = 0
            domain.backupBegin(backup_xml, checkpoint_xml, flags)

            # Parse backup XML to get NBD socket paths
            nbd_info = self._parse_backup_info(domain)

            self._log("INFO", f"Backup started, NBD exports ready", {
                "disks": list(nbd_info.keys())
            })

            return nbd_info

        except libvirt.libvirtError as e:
            error_msg = f"Failed to start backup: {e}"
            self._log("ERROR", error_msg)
            raise CheckpointError(error_msg)

    def _build_backup_xml(
        self,
        disk_targets: List[str],
        scratch_dir: str,
        incremental_from: Optional[str] = None
    ) -> str:
        """
        Build backup XML for pull-mode backup.

        Args:
            disk_targets: List of disk targets
            scratch_dir: Scratch directory path
            incremental_from: Previous checkpoint for incremental

        Returns:
            Backup XML string
        """
        root = ET.Element("domainbackup")
        root.set("mode", "pull")

        if incremental_from:
            incremental_elem = ET.SubElement(root, "incremental")
            incremental_elem.text = incremental_from

        # Server element for NBD
        server_elem = ET.SubElement(root, "server")
        server_elem.set("transport", "unix")
        server_elem.set("socket", f"{scratch_dir}/backup.sock")

        disks_elem = ET.SubElement(root, "disks")
        for target in disk_targets:
            disk_elem = ET.SubElement(disks_elem, "disk")
            disk_elem.set("name", target)
            disk_elem.set("backup", "yes")
            disk_elem.set("type", "file")

            # Scratch file for backup data
            scratch_elem = ET.SubElement(disk_elem, "scratch")
            scratch_elem.set("file", f"{scratch_dir}/scratch-{target}.qcow2")

        return ET.tostring(root, encoding="unicode")

    def _parse_backup_info(self, domain: libvirt.virDomain) -> Dict[str, Dict[str, str]]:
        """
        Parse active backup info to get NBD connection details.

        Args:
            domain: Libvirt domain

        Returns:
            Dictionary mapping disk target to NBD info
        """
        try:
            backup_xml = domain.backupGetXMLDesc(0)
            root = ET.fromstring(backup_xml)

            result = {}

            # Get server socket
            server = root.find("server")
            socket_path = server.get("socket") if server is not None else None

            # Get disk exports
            for disk in root.findall(".//disk[@backup='yes']"):
                target = disk.get("name")
                if target:
                    result[target] = {
                        "socket": socket_path,
                        "export_name": target
                    }

            return result

        except Exception as e:
            logger.error(f"Failed to parse backup info: {e}")
            return {}

    def stop_backup(self, domain: libvirt.virDomain) -> None:
        """
        Stop an active backup.

        Args:
            domain: Libvirt domain

        Raises:
            CheckpointError: If stop fails
        """
        self._log("INFO", f"Stopping backup for domain {domain.name()}")

        try:
            domain.backupEnd(0)
            self._log("INFO", "Backup stopped successfully")
        except libvirt.libvirtError as e:
            # Ignore error if no backup is active
            if "backup job is not active" not in str(e).lower():
                raise CheckpointError(f"Failed to stop backup: {e}")

    def is_backup_active(self, domain: libvirt.virDomain) -> bool:
        """
        Check if a backup is currently active.

        Args:
            domain: Libvirt domain

        Returns:
            True if backup is active
        """
        try:
            domain.backupGetXMLDesc(0)
            return True
        except libvirt.libvirtError:
            return False

    def cleanup_old_checkpoints(
        self,
        domain: libvirt.virDomain,
        keep_latest: int = 1
    ) -> int:
        """
        Clean up old checkpoints, keeping only the most recent ones.

        Args:
            domain: Libvirt domain
            keep_latest: Number of recent checkpoints to keep

        Returns:
            Number of checkpoints deleted
        """
        checkpoints = self.list_checkpoints(domain)

        if len(checkpoints) <= keep_latest:
            return 0

        # Sort by name (assuming names include timestamps)
        checkpoints.sort()

        # Delete oldest checkpoints
        to_delete = checkpoints[:-keep_latest] if keep_latest > 0 else checkpoints
        deleted = 0

        for cp_name in to_delete:
            if self.delete_checkpoint(domain, cp_name):
                deleted += 1

        self._log("INFO", f"Cleaned up {deleted} old checkpoints")
        return deleted
