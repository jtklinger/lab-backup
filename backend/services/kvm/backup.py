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

    async def list_storage_pools(self, uri: str) -> Dict[str, Any]:
        """
        List all storage pools on a KVM host and detect their types.

        Returns:
            Dictionary with storage capabilities:
            - supports_file: bool
            - file_storage_path: Optional[str]
            - supports_rbd: bool
            - rbd_default_pool: Optional[str]
        """
        try:
            conn = await self._run_in_executor(self._get_connection, uri)

            def _list_pools():
                pools = conn.listAllStoragePools()

                capabilities = {
                    "supports_file": False,
                    "file_storage_path": None,
                    "supports_rbd": False,
                    "rbd_default_pool": None,
                }

                for pool in pools:
                    try:
                        # Only consider active pools
                        if not pool.isActive():
                            continue

                        pool_name = pool.name()
                        pool_xml = pool.XMLDesc(0)
                        pool_root = ET.fromstring(pool_xml)

                        pool_type = pool_root.get("type")

                        # Check for file-based storage (dir, fs, etc.)
                        if pool_type in ["dir", "fs", "netfs", "logical", "disk"]:
                            capabilities["supports_file"] = True
                            # Get the path from the pool XML
                            target = pool_root.find(".//target/path")
                            if target is not None and target.text:
                                # Use the first file storage path we find
                                if not capabilities["file_storage_path"]:
                                    capabilities["file_storage_path"] = target.text

                        # Check for RBD/Ceph storage
                        elif pool_type == "rbd":
                            capabilities["supports_rbd"] = True
                            # Use the first RBD pool name we find as default
                            if not capabilities["rbd_default_pool"]:
                                capabilities["rbd_default_pool"] = pool_name

                    except Exception as e:
                        logger.warning(f"Error processing pool {pool.name()}: {e}")
                        continue

                return capabilities

            return await self._run_in_executor(_list_pools)

        except libvirt.libvirtError as e:
            logger.error(f"Failed to list storage pools: {e}")
            # Raise exception so fallback to static config can happen
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
                    disk_type = disk.get("type")
                    source = disk.find("source")
                    target = disk.find("target")
                    driver = disk.find("driver")

                    if source is not None and target is not None:
                        disk_info = {
                            "target": target.get("dev"),
                            "bus": target.get("bus"),
                            "type": disk_type
                        }

                        # Handle different disk types
                        if disk_type == "file":
                            # Local file-based disk
                            disk_path = source.get("file") or source.get("dev")
                            if disk_path:
                                disk_info["path"] = disk_path
                                disk_info["format"] = driver.get("type") if driver is not None else "raw"
                                disks.append(disk_info)
                        elif disk_type == "network":
                            # Network-based disk (RBD, iSCSI, etc.)
                            protocol = source.get("protocol")
                            if protocol == "rbd":
                                # Ceph RBD disk
                                rbd_name = source.get("name")
                                if rbd_name:
                                    disk_info["protocol"] = protocol
                                    disk_info["rbd_name"] = rbd_name
                                    disk_info["format"] = driver.get("type") if driver is not None else "raw"
                                    # Extract pool and image name
                                    if "/" in rbd_name:
                                        disk_info["rbd_pool"], disk_info["rbd_image"] = rbd_name.split("/", 1)
                                    disks.append(disk_info)

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

                # Extract hostname from URI for SSH commands
                import re
                ssh_match = re.search(r'ssh://([^@]+@)?([^:/]+)', uri)
                ssh_host = None
                if ssh_match:
                    ssh_user = ssh_match.group(1).rstrip('@') if ssh_match.group(1) else None
                    ssh_hostname = ssh_match.group(2)
                    ssh_host = f"{ssh_user}@{ssh_hostname}" if ssh_user else ssh_hostname

                for disk in disks:
                    disk_type = disk.get("type")
                    target = disk["target"]

                    if disk_type == "file":
                        # File-based disk
                        disk_path = Path(disk["path"])

                        # For file-based disks over SSH, we need to copy from remote host
                        if ssh_host:
                            dest_disk = backup_dir / f"{target}.img"
                            logger.info(f"Copying file-based disk from remote host: {disk_path}")

                            import subprocess
                            try:
                                # Use SCP to copy the disk file from remote host
                                cmd = ["scp", f"{ssh_host}:{disk_path}", str(dest_disk)]
                                subprocess.run(cmd, check=True, capture_output=True, text=True)
                                disk_size = dest_disk.stat().st_size
                            except subprocess.CalledProcessError as e:
                                logger.error(f"SCP failed for {target}: {e.stderr}")
                                continue
                        else:
                            # Local libvirt - direct file access
                            if not disk_path.exists():
                                logger.warning(f"Disk not found: {disk_path}")
                                continue

                            dest_disk = backup_dir / f"{target}.qcow2"

                            # Determine backup method based on incremental flag
                            if incremental and disk_path.suffix in [".qcow2", ".qed"]:
                                logger.info(f"Creating incremental backup of disk: {target}")
                                import subprocess
                                try:
                                    cmd = [
                                        "qemu-img", "create",
                                        "-f", "qcow2",
                                        "-b", str(disk_path),
                                        "-F", "qcow2",
                                        str(dest_disk)
                                    ]
                                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                                except subprocess.CalledProcessError as e:
                                    logger.error(f"qemu-img failed for {target}: {e.stderr}")
                                    import shutil
                                    shutil.copy2(disk_path, dest_disk)
                            else:
                                # Full backup - copy entire disk image
                                logger.info(f"Creating full backup of disk: {target} ({disk_path})")
                                import shutil
                                shutil.copy2(disk_path, dest_disk)

                            disk_size = dest_disk.stat().st_size

                    elif disk_type == "network" and disk.get("protocol") == "rbd":
                        # RBD/Ceph disk - export via SSH using qemu-img convert
                        # qemu-img on KVM host can directly access RBD images
                        rbd_pool = disk.get("rbd_pool", "")
                        rbd_image = disk.get("rbd_image", "")
                        rbd_name = disk.get("rbd_name", "")

                        if not ssh_host:
                            logger.error(f"RBD backup requires SSH connection, but URI is local: {uri}")
                            continue

                        dest_disk = backup_dir / f"{target}.img"
                        logger.info(f"Exporting RBD disk: {rbd_name} (30 GB, this will take some time)")

                        import subprocess
                        import uuid
                        try:
                            # Use a two-step approach:
                            # 1. Convert RBD to temp file on KVM host using qemu-img
                            # 2. Stream temp file via SSH and delete it

                            temp_filename = f"/tmp/backup_{uuid.uuid4().hex[:8]}.img"
                            logger.info(f"Step 1: Converting RBD to temp file on KVM host: {temp_filename}")

                            # Step 1: Convert RBD to file on KVM host
                            convert_cmd = [
                                "ssh", ssh_host,
                                "qemu-img", "convert",
                                "-O", "raw",
                                f"rbd:{rbd_name}",
                                temp_filename
                            ]

                            subprocess.run(
                                convert_cmd,
                                stderr=subprocess.PIPE,
                                check=True,
                                text=False,
                                timeout=7200  # 2 hour timeout for large disks
                            )

                            logger.info(f"Step 2: Streaming temp file to worker and cleaning up")

                            # Step 2: Stream file back and delete it
                            # Use && to ensure cleanup happens even if successful
                            stream_cmd = [
                                "ssh", ssh_host,
                                f"cat {temp_filename} && rm -f {temp_filename}"
                            ]

                            with open(dest_disk, 'wb') as f:
                                subprocess.run(
                                    stream_cmd,
                                    stdout=f,
                                    stderr=subprocess.PIPE,
                                    check=True,
                                    text=False,
                                    timeout=3600  # 1 hour for transfer
                                )

                            disk_size = dest_disk.stat().st_size
                            logger.info(f"Exported RBD disk {rbd_name}: {disk_size} bytes ({disk_size / 1024**3:.2f} GB)")

                        except subprocess.CalledProcessError as e:
                            error_msg = e.stderr.decode() if e.stderr else str(e)
                            logger.error(f"RBD export failed for {target}: {error_msg}")
                            # Try to clean up temp file
                            try:
                                subprocess.run(["ssh", ssh_host, f"rm -f {temp_filename}"], timeout=30)
                            except:
                                pass
                            continue
                        except subprocess.TimeoutExpired:
                            logger.error(f"RBD export for {target} timed out")
                            # Try to clean up temp file
                            try:
                                subprocess.run(["ssh", ssh_host, f"rm -f {temp_filename}"], timeout=30)
                            except:
                                pass
                            continue
                        except Exception as e:
                            logger.error(f"Unexpected error exporting RBD disk {target}: {e}")
                            # Try to clean up temp file
                            try:
                                subprocess.run(["ssh", ssh_host, f"rm -f {temp_filename}"], timeout=30)
                            except:
                                pass
                            continue
                    else:
                        logger.warning(f"Unsupported disk type: {disk_type} for disk {target}")
                        continue

                    total_size += disk_size

                    backed_up_disks.append({
                        "target": target,
                        "file": dest_disk.name,
                        "size": disk_size,
                        "type": disk_type,
                        "incremental": incremental and disk_type == "file" and disk.get("path", "").endswith((".qcow2", ".qed"))
                    })

                    logger.info(f"Backed up disk: {target} ({disk_size} bytes)")

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

    async def restore_vm(
        self,
        uri: str,
        backup_dir: Path,
        new_name: Optional[str] = None,
        overwrite: bool = False,
        storage_type: str = "auto",
        storage_config: Optional[dict] = None,
        host_config: Optional[dict] = None
    ) -> Dict[str, Any]:
        """
        Restore a VM from a backup with flexible storage destination.

        Args:
            uri: Libvirt connection URI
            backup_dir: Directory containing the extracted backup files
            new_name: Optional new name for the restored VM
            overwrite: Whether to overwrite existing VM with the same name
            storage_type: Storage type: "auto" (detect from backup), "file", or "rbd"
            storage_config: Optional storage-specific configuration override
            host_config: KVM host configuration containing RBD settings

        Returns:
            Dictionary with restore information
        """
        try:
            conn = await self._run_in_executor(self._get_connection, uri)

            def _restore():
                # Read VM info
                info_file = backup_dir / "vm_info.json"
                if not info_file.exists():
                    raise Exception("vm_info.json not found in backup")

                with open(info_file, 'r') as f:
                    vm_info = json.load(f)

                original_name = vm_info["name"]
                restore_name = new_name if new_name else original_name

                logger.info(f"Restoring VM: {original_name} as {restore_name}")

                # Check if VM already exists
                try:
                    existing_domain = conn.lookupByName(restore_name)
                    if not overwrite:
                        raise Exception(f"VM '{restore_name}' already exists. Use overwrite=True to replace it.")

                    # Undefine existing VM
                    logger.info(f"Undefining existing VM: {restore_name}")
                    existing_domain.undefineFlags(
                        libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE |
                        libvirt.VIR_DOMAIN_UNDEFINE_NVRAM
                    )
                except libvirt.libvirtError:
                    # VM doesn't exist - that's fine
                    pass

                # Read and modify domain XML
                xml_file = backup_dir / "domain.xml"
                if not xml_file.exists():
                    raise Exception("domain.xml not found in backup")

                with open(xml_file, 'r') as f:
                    xml_content = f.read()

                # Parse XML
                root = ET.fromstring(xml_content)

                # Update VM name if specified
                if new_name:
                    name_elem = root.find("name")
                    if name_elem is not None:
                        name_elem.text = new_name

                # Remove UUID to get a new one assigned
                uuid_elem = root.find("uuid")
                if uuid_elem is not None:
                    root.remove(uuid_elem)

                # Extract hostname from URI for SSH commands
                import re
                ssh_match = re.search(r'ssh://([^@]+@)?([^:/]+)', uri)
                ssh_host = None
                if ssh_match:
                    ssh_user = ssh_match.group(1).rstrip('@') if ssh_match.group(1) else None
                    ssh_hostname = ssh_match.group(2)
                    ssh_host = f"{ssh_user}@{ssh_hostname}" if ssh_user else ssh_hostname

                # Get storage configuration
                host_cfg = host_config or {}
                storage_cfg = host_cfg.get("storage", {})
                file_storage_path = storage_cfg.get("file_storage_path", "/var/lib/libvirt/images")
                rbd_cfg = storage_cfg.get("rbd", {})

                # Get original disk information from vm_info.json to detect types
                original_disks = {disk["target"]: disk for disk in vm_info.get("disks", [])}

                # Update disk paths
                restored_disks = []
                for disk_elem in root.findall(".//disk[@device='disk']"):
                    source_elem = disk_elem.find("source")
                    target_elem = disk_elem.find("target")

                    if source_elem is None or target_elem is None:
                        continue

                    target_dev = target_elem.get("dev")

                    # Find corresponding disk file in backup directory
                    disk_file = None
                    for ext in ['.img', '.qcow2', '.raw']:
                        candidate = backup_dir / f"{target_dev}{ext}"
                        if candidate.exists():
                            disk_file = candidate
                            logger.info(f"Found disk file for {target_dev}: {candidate.name}")
                            break

                    if not disk_file:
                        logger.warning(f"Disk file not found for {target_dev}, skipping")
                        continue

                    # Determine target storage type
                    original_disk = original_disks.get(target_dev, {})
                    original_disk_type = original_disk.get("type", "file")
                    original_protocol = original_disk.get("protocol")

                    # Decide target storage type
                    if storage_type == "auto":
                        # Auto-detect from original
                        if original_disk_type == "network" and original_protocol == "rbd":
                            target_storage_type = "rbd"
                        else:
                            target_storage_type = "file"
                    else:
                        target_storage_type = storage_type

                    # Restore based on target storage type
                    if target_storage_type == "rbd":
                        # Restore to RBD/Ceph
                        rbd_pool = original_disk.get("rbd_pool") or rbd_cfg.get("default_pool", "vms")
                        rbd_image = f"{restore_name}-{target_dev}"

                        logger.info(f"Uploading disk {target_dev} to RBD: {rbd_pool}/{rbd_image}")

                        if not ssh_host:
                            raise Exception("RBD restore requires SSH connection to KVM host")

                        import subprocess
                        try:
                            # Upload to RBD using qemu-img convert over SSH
                            # Stream the disk image via stdin to avoid temp files on remote host
                            cmd = [
                                "ssh", ssh_host,
                                "qemu-img", "convert",
                                "-f", "raw",
                                "-O", "raw",
                                "-p",  # Show progress
                                "-",   # Read from stdin
                                f"rbd:{rbd_pool}/{rbd_image}"
                            ]

                            with open(disk_file, 'rb') as f:
                                result = subprocess.run(
                                    cmd,
                                    stdin=f,
                                    capture_output=True,
                                    text=True,
                                    check=True,
                                    timeout=7200  # 2 hour timeout for large disks
                                )

                            logger.info(f"Uploaded disk {target_dev} to RBD: {rbd_pool}/{rbd_image}")

                            # Update XML for RBD disk
                            disk_elem.set("type", "network")
                            disk_elem.set("device", "disk")

                            # Clear old source and rebuild for RBD
                            source_elem.clear()
                            source_elem.set("protocol", "rbd")
                            source_elem.set("name", f"{rbd_pool}/{rbd_image}")

                            # Add Ceph monitor hosts
                            for monitor in rbd_cfg.get("monitors", []):
                                host_elem = ET.SubElement(source_elem, "host")
                                host_elem.set("name", monitor["host"])
                                host_elem.set("port", str(monitor["port"]))

                            # Add authentication if configured
                            if rbd_cfg.get("auth_username"):
                                # Remove existing auth if present
                                existing_auth = disk_elem.find("auth")
                                if existing_auth is not None:
                                    disk_elem.remove(existing_auth)

                                auth_elem = ET.SubElement(disk_elem, "auth")
                                auth_elem.set("username", rbd_cfg["auth_username"])
                                secret_elem = ET.SubElement(auth_elem, "secret")
                                secret_elem.set("type", "ceph")
                                secret_elem.set("uuid", rbd_cfg["secret_uuid"])

                            # Ensure driver is set correctly for RBD
                            driver_elem = disk_elem.find("driver")
                            if driver_elem is None:
                                driver_elem = ET.SubElement(disk_elem, "driver")
                            driver_elem.set("name", "qemu")
                            driver_elem.set("type", "raw")

                            restored_disks.append({
                                "target": target_dev,
                                "type": "rbd",
                                "pool": rbd_pool,
                                "image": rbd_image,
                                "size": disk_file.stat().st_size
                            })

                        except subprocess.CalledProcessError as e:
                            logger.error(f"RBD upload failed for {target_dev}: {e.stderr}")
                            raise Exception(f"Failed to upload disk {target_dev} to RBD: {e.stderr}")
                        except subprocess.TimeoutExpired:
                            logger.error(f"RBD upload for {target_dev} timed out")
                            raise Exception(f"RBD upload for {target_dev} timed out after 2 hours")

                    else:
                        # Restore to file storage
                        new_disk_name = f"{restore_name}-{target_dev}.img"
                        new_disk_path = f"{file_storage_path}/{new_disk_name}"

                        logger.info(f"Copying disk {target_dev} to file: {new_disk_path}")

                        if ssh_host:
                            # Remote host - use SCP
                            import subprocess
                            try:
                                cmd = ["scp", str(disk_file), f"{ssh_host}:{new_disk_path}"]
                                subprocess.run(cmd, check=True, capture_output=True, text=True)
                                logger.info(f"Disk copied via SCP: {new_disk_path}")
                            except subprocess.CalledProcessError as e:
                                logger.error(f"SCP failed for {target_dev}: {e.stderr}")
                                raise Exception(f"Failed to copy disk {target_dev}: {e.stderr}")
                        else:
                            # Local host - direct copy
                            import shutil
                            shutil.copy2(disk_file, new_disk_path)
                            logger.info(f"Disk copied locally: {new_disk_path}")

                        # Update XML for file disk
                        disk_elem.set("type", "file")
                        source_elem.clear()
                        source_elem.set("file", new_disk_path)

                        restored_disks.append({
                            "target": target_dev,
                            "type": "file",
                            "path": new_disk_path,
                            "size": disk_file.stat().st_size
                        })

                # Convert XML back to string
                modified_xml = ET.tostring(root, encoding='unicode')

                # Define the VM
                logger.info(f"Defining restored VM: {restore_name}")
                domain = conn.defineXML(modified_xml)

                new_uuid = domain.UUIDString()
                logger.info(f"VM restored successfully. UUID: {new_uuid}")

                return {
                    "vm_name": restore_name,
                    "vm_uuid": new_uuid,
                    "original_name": original_name,
                    "disks": restored_disks,
                    "overwritten": overwrite
                }

            return await self._run_in_executor(_restore)

        except libvirt.libvirtError as e:
            logger.error(f"Failed to restore VM: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during restore: {e}")
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
