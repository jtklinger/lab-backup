"""
KVM/libvirt backup service.
"""
import asyncio
import tempfile
import tarfile
import json
from pathlib import Path
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import libvirt
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)


class KVMBackupService:
    """Service for backing up KVM virtual machines using libvirt."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.connections: Dict[str, libvirt.virConnect] = {}

    async def _run_in_executor(self, func, *args):
        """Run blocking libvirt call in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args)

    def _get_connection(self, uri: str) -> libvirt.virConnect:
        """Get or create libvirt connection."""
        if uri not in self.connections:
            try:
                conn = libvirt.open(uri)
                if conn is None:
                    raise Exception(f"Failed to connect to libvirt URI: {uri}")
                self.connections[uri] = conn
                logger.info(f"Connected to libvirt host: {uri}")
            except libvirt.libvirtError as e:
                logger.error(f"Failed to connect to libvirt: {e}")
                raise

        return self.connections[uri]

    async def test_connection(self, uri: str) -> bool:
        """Test connection to KVM host."""
        try:
            conn = await self._run_in_executor(self._get_connection, uri)
            # Test by getting hostname
            await self._run_in_executor(conn.getHostname)
            return True
        except Exception as e:
            logger.error(f"KVM connection test failed: {e}")
            return False

    async def list_vms(self, uri: str) -> list[Dict[str, Any]]:
        """List all VMs on a KVM host."""
        try:
            conn = await self._run_in_executor(self._get_connection, uri)

            # Get all domains (both active and inactive)
            def _list_all():
                domains = conn.listAllDomains()
                vms = []
                for domain in domains:
                    info = domain.info()
                    vms.append({
                        "name": domain.name(),
                        "uuid": domain.UUIDString(),
                        "state": self._get_state_name(info[0]),
                        "vcpus": info[3],
                        "memory": info[2] // 1024,  # Convert to MB
                    })
                return vms

            return await self._run_in_executor(_list_all)

        except libvirt.libvirtError as e:
            logger.error(f"Failed to list VMs: {e}")
            raise

    def _get_state_name(self, state: int) -> str:
        """Convert libvirt state code to name."""
        states = {
            libvirt.VIR_DOMAIN_NOSTATE: "no_state",
            libvirt.VIR_DOMAIN_RUNNING: "running",
            libvirt.VIR_DOMAIN_BLOCKED: "blocked",
            libvirt.VIR_DOMAIN_PAUSED: "paused",
            libvirt.VIR_DOMAIN_SHUTDOWN: "shutdown",
            libvirt.VIR_DOMAIN_SHUTOFF: "shutoff",
            libvirt.VIR_DOMAIN_CRASHED: "crashed",
            libvirt.VIR_DOMAIN_PMSUSPENDED: "suspended",
        }
        return states.get(state, "unknown")

    async def create_backup(
        self,
        uri: str,
        vm_uuid: str,
        backup_dir: Path,
        incremental: bool = False,
        parent_backup: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a backup of a VM.

        Args:
            uri: Libvirt connection URI
            vm_uuid: UUID of the VM to backup
            backup_dir: Directory to store backup files
            incremental: Whether to create incremental backup
            parent_backup: Path to parent backup for incremental

        Returns:
            Dictionary with backup information
        """
        try:
            conn = await self._run_in_executor(self._get_connection, uri)

            def _backup():
                # Get domain by UUID
                domain = conn.lookupByUUIDString(vm_uuid)
                vm_name = domain.name()

                logger.info(f"Starting backup of VM: {vm_name} ({vm_uuid})")

                # Get VM XML configuration
                xml_desc = domain.XMLDesc(0)

                # Parse XML to get disk information
                root = ET.fromstring(xml_desc)
                disks = []

                for disk in root.findall(".//disk[@device='disk']"):
                    source = disk.find("source")
                    target = disk.find("target")

                    if source is not None and target is not None:
                        # Get disk source path
                        disk_path = source.get("file") or source.get("dev")
                        if disk_path:
                            disks.append({
                                "path": disk_path,
                                "target": target.get("dev"),
                                "bus": target.get("bus")
                            })

                # Create backup directory
                backup_dir.mkdir(parents=True, exist_ok=True)

                # Save VM XML configuration
                xml_file = backup_dir / "domain.xml"
                with open(xml_file, 'w') as f:
                    f.write(xml_desc)

                # Get VM info
                info = domain.info()
                vm_info = {
                    "name": vm_name,
                    "uuid": vm_uuid,
                    "state": self._get_state_name(info[0]),
                    "vcpus": info[3],
                    "memory": info[2] // 1024,
                    "disks": disks
                }

                # Save VM info
                info_file = backup_dir / "vm_info.json"
                with open(info_file, 'w') as f:
                    json.dump(vm_info, f, indent=2)

                # Create snapshot for consistent backup (if VM is running)
                snapshot_name = f"backup-{vm_name}"
                snapshot_created = False

                if info[0] == libvirt.VIR_DOMAIN_RUNNING:
                    try:
                        # Create external snapshot XML
                        snapshot_xml = f"""
                        <domainsnapshot>
                            <name>{snapshot_name}</name>
                            <description>Backup snapshot</description>
                        </domainsnapshot>
                        """
                        domain.snapshotCreateXML(
                            snapshot_xml,
                            libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY
                        )
                        snapshot_created = True
                        logger.info(f"Created snapshot for VM: {vm_name}")
                    except libvirt.libvirtError as e:
                        logger.warning(f"Failed to create snapshot (proceeding anyway): {e}")

                # Backup disk images
                total_size = 0
                backed_up_disks = []

                for disk in disks:
                    disk_path = Path(disk["path"])
                    if not disk_path.exists():
                        logger.warning(f"Disk not found: {disk_path}")
                        continue

                    # Determine backup method based on disk format
                    if incremental and parent_backup and disk_path.suffix == ".qcow2":
                        # Use qemu-img to create incremental backup
                        # This would require qemu-img command execution
                        logger.info(f"Creating incremental backup of disk: {disk['target']}")
                        # For now, we'll do a full copy
                        # TODO: Implement proper incremental backup using qemu-img
                        pass

                    # Copy disk image
                    dest_disk = backup_dir / f"{disk['target']}.qcow2"
                    logger.info(f"Backing up disk: {disk['target']} ({disk_path})")

                    # Use cp command for efficiency (could use qemu-img convert)
                    import shutil
                    shutil.copy2(disk_path, dest_disk)

                    disk_size = dest_disk.stat().st_size
                    total_size += disk_size

                    backed_up_disks.append({
                        "target": disk["target"],
                        "file": dest_disk.name,
                        "size": disk_size
                    })

                    logger.info(f"Backed up disk: {disk['target']} ({disk_size} bytes)")

                # Delete snapshot if created
                if snapshot_created:
                    try:
                        snapshot = domain.snapshotLookupByName(snapshot_name)
                        snapshot.delete(libvirt.VIR_DOMAIN_SNAPSHOT_DELETE_METADATA_ONLY)
                        logger.info(f"Deleted snapshot for VM: {vm_name}")
                    except libvirt.libvirtError as e:
                        logger.warning(f"Failed to delete snapshot: {e}")

                return {
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "state": self._get_state_name(info[0]),
                    "disks": backed_up_disks,
                    "total_size": total_size,
                    "backup_dir": str(backup_dir),
                    "incremental": incremental
                }

            return await self._run_in_executor(_backup)

        except libvirt.libvirtError as e:
            logger.error(f"Failed to backup VM: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during backup: {e}")
            raise

    async def create_backup_archive(
        self,
        backup_dir: Path,
        output_file: Path,
        compression: str = "gzip"
    ) -> Dict[str, Any]:
        """
        Create a compressed archive of the backup.

        Args:
            backup_dir: Directory containing backup files
            output_file: Output archive file path
            compression: Compression type (gzip, bz2, xz, none)

        Returns:
            Dictionary with archive information
        """
        try:
            def _create_archive():
                mode_map = {
                    "gzip": "w:gz",
                    "bz2": "w:bz2",
                    "xz": "w:xz",
                    "none": "w"
                }

                mode = mode_map.get(compression, "w:gz")

                with tarfile.open(output_file, mode) as tar:
                    tar.add(backup_dir, arcname=backup_dir.name)

                archive_size = output_file.stat().st_size
                original_size = sum(
                    f.stat().st_size
                    for f in backup_dir.rglob("*")
                    if f.is_file()
                )

                return {
                    "archive_path": str(output_file),
                    "original_size": original_size,
                    "compressed_size": archive_size,
                    "compression_ratio": original_size / archive_size if archive_size > 0 else 0
                }

            return await self._run_in_executor(_create_archive)

        except Exception as e:
            logger.error(f"Failed to create backup archive: {e}")
            raise

    async def get_vm_info(self, uri: str, vm_uuid: str) -> Dict[str, Any]:
        """Get detailed information about a VM."""
        try:
            conn = await self._run_in_executor(self._get_connection, uri)

            def _get_info():
                domain = conn.lookupByUUIDString(vm_uuid)
                info = domain.info()
                xml_desc = domain.XMLDesc(0)

                # Parse XML for disk information
                root = ET.fromstring(xml_desc)
                disks = []
                total_disk_size = 0

                for disk in root.findall(".//disk[@device='disk']"):
                    source = disk.find("source")
                    target = disk.find("target")

                    if source is not None and target is not None:
                        disk_path = source.get("file") or source.get("dev")
                        if disk_path and Path(disk_path).exists():
                            disk_size = Path(disk_path).stat().st_size
                            total_disk_size += disk_size
                            disks.append({
                                "path": disk_path,
                                "target": target.get("dev"),
                                "bus": target.get("bus"),
                                "size": disk_size
                            })

                return {
                    "name": domain.name(),
                    "uuid": vm_uuid,
                    "state": self._get_state_name(info[0]),
                    "vcpus": info[3],
                    "memory": info[2] // 1024,
                    "disks": disks,
                    "total_disk_size": total_disk_size
                }

            return await self._run_in_executor(_get_info)

        except libvirt.libvirtError as e:
            logger.error(f"Failed to get VM info: {e}")
            raise

    def close_connections(self):
        """Close all libvirt connections."""
        for uri, conn in self.connections.items():
            try:
                conn.close()
                logger.info(f"Closed connection to: {uri}")
            except Exception as e:
                logger.error(f"Error closing connection to {uri}: {e}")

        self.connections.clear()
