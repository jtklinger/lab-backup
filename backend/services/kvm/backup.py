"""
KVM/libvirt backup service.
"""
import asyncio
import os
import re
import tempfile
import tarfile
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor
import libvirt
import xml.etree.ElementTree as ET
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.kvm.ssh_manager import SSHKeyManager

logger = logging.getLogger(__name__)


class KVMBackupService:
    """Service for backing up KVM virtual machines using libvirt."""

    def __init__(self, log_callback=None):
        """
        Initialize the KVM backup service.

        Args:
            log_callback: Optional callback function for verbose logging.
                          Signature: callback(level: str, message: str, details: dict = None)
                          This allows the worker to capture detailed logs for job tracking.
        """
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.connections: Dict[str, libvirt.virConnect] = {}
        # Store auth credentials per URI for automatic use
        self.auth_credentials: Dict[str, tuple[Optional[str], Optional[str]]] = {}  # uri -> (password, username)
        self.log_callback = log_callback

    def _log(self, level: str, message: str, details: dict = None):
        """
        Log a message to both the Python logger and the callback (if set).

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Human-readable log message
            details: Optional structured metadata
        """
        # Always log to Python logger
        log_method = getattr(logger, level.lower(), logger.info)
        log_method(message)

        # Call the callback if set (for job log tracking)
        if self.log_callback:
            try:
                self.log_callback(level, message, details)
            except Exception as e:
                logger.warning(f"Log callback failed: {e}")

    async def _run_in_executor(self, func, *args):
        """Run blocking libvirt call in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args)

    @staticmethod
    def _extract_hostname_from_uri(uri: str) -> Optional[str]:
        """
        Extract hostname from a libvirt URI.

        Args:
            uri: libvirt URI (e.g., qemu+ssh://user@hostname/system)

        Returns:
            Hostname or None if not found
        """
        # Match pattern: qemu+ssh://[user@]hostname[:port]/system
        match = re.search(r'qemu\+(?:ssh|tcp|tls)://(?:[^@]+@)?([^:/]+)', uri)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_username_from_uri(uri: str) -> Optional[str]:
        """
        Extract username from a libvirt URI.

        Args:
            uri: libvirt URI (e.g., qemu+tcp://user@hostname/system)

        Returns:
            Username or None if not found
        """
        # Match pattern: qemu+tcp://username@hostname/system
        match = re.search(r'qemu\+(?:tcp|tls)://([^@]+)@', uri)
        if match:
            return match.group(1)
        return None

    async def setup_auth_for_host(
        self,
        db: AsyncSession,
        kvm_host_id: int
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Get authentication credentials for a KVM host from database.

        This will:
        1. Query the KVM host from database
        2. If auth_type is 'password', decrypt and return password
        3. Store credentials in self.auth_credentials for automatic use
        4. Return (password, username) tuple

        Args:
            db: Database session
            kvm_host_id: ID of the KVM host

        Returns:
            Tuple of (password, username) - both None if not using password auth
        """
        from backend.models.infrastructure import KVMHost
        from backend.core.encryption import decrypt_password
        from backend.core.config import settings
        from sqlalchemy import select

        try:
            # Query KVM host
            result = await db.execute(
                select(KVMHost).where(KVMHost.id == kvm_host_id)
            )
            kvm_host = result.scalar_one_or_none()

            if not kvm_host:
                logger.warning(f"KVM host {kvm_host_id} not found")
                return None, None

            # Check if using password authentication
            if kvm_host.auth_type == "password" and kvm_host.password_encrypted:
                # Decrypt password
                password = decrypt_password(
                    kvm_host.password_encrypted,
                    settings.SECRET_KEY
                )
                username = kvm_host.username

                # Store credentials for automatic use with this URI
                self.auth_credentials[kvm_host.uri] = (password, username)

                logger.debug(f"Retrieved password authentication for KVM host {kvm_host_id}")
                return password, username
            else:
                logger.debug(f"KVM host {kvm_host_id} not using password authentication")
                return None, None

        except Exception as e:
            logger.error(f"Failed to get authentication for KVM host {kvm_host_id}: {e}")
            raise

    async def setup_ssh_key_for_host(
        self,
        db: AsyncSession,
        kvm_host_id: int,
        uri: str
    ) -> bool:
        """
        Set up SSH key from database for a KVM host.

        This will:
        1. Check if there's an SSH key in the database
        2. If yes, decrypt and write to ~/.ssh/kvm_host_{id}_key
        3. Update ~/.ssh/config to use that key for the specific hostname
        4. Return True if database key was set up, False otherwise

        Args:
            db: Database session
            kvm_host_id: ID of the KVM host
            uri: libvirt URI for the host

        Returns:
            True if database SSH key was configured, False if using default keys
        """
        # Extract hostname from URI
        hostname = self._extract_hostname_from_uri(uri)
        if not hostname:
            logger.warning(f"Could not extract hostname from URI: {uri}")
            return False

        # Check for database SSH key
        ssh_manager = SSHKeyManager(db)
        ssh_key = await ssh_manager.get_ssh_key(kvm_host_id)

        if not ssh_key:
            logger.debug(f"No database SSH key for KVM host {kvm_host_id}, using default keys")
            return False

        try:
            # Decrypt the private key
            private_key = await ssh_manager.decrypt_key(ssh_key)

            # Determine key filename based on type
            key_filename = f"kvm_host_{kvm_host_id}_key"
            key_path = os.path.expanduser(f"~/.ssh/{key_filename}")

            # Write the private key
            with open(key_path, 'w') as f:
                f.write(private_key)

            # Set proper permissions
            os.chmod(key_path, 0o600)

            logger.info(f"Wrote database SSH key to {key_path}")

            # Update ~/.ssh/config to use this key for the specific host
            ssh_config_path = os.path.expanduser("~/.ssh/config")

            # Read existing config
            existing_config = ""
            if os.path.exists(ssh_config_path):
                with open(ssh_config_path, 'r') as f:
                    existing_config = f.read()

            # Check if there's already a config entry for this host
            host_pattern = f"Host {hostname}"
            identity_line = f"    IdentityFile ~/.ssh/{key_filename}"

            if host_pattern in existing_config:
                # Update existing entry - replace or add IdentityFile line
                lines = existing_config.split('\n')
                new_lines = []
                in_host_block = False
                identity_added = False

                for line in lines:
                    if line.startswith(f"Host {hostname}"):
                        in_host_block = True
                        new_lines.append(line)
                    elif line.startswith("Host ") and in_host_block:
                        # End of our host block
                        if not identity_added:
                            new_lines.append(identity_line)
                            identity_added = True
                        in_host_block = False
                        new_lines.append(line)
                    elif in_host_block and line.strip().startswith("IdentityFile"):
                        # Replace existing IdentityFile
                        new_lines.append(identity_line)
                        identity_added = True
                    else:
                        new_lines.append(line)

                # If we didn't add identity (host block was at end), add it now
                if in_host_block and not identity_added:
                    new_lines.append(identity_line)

                updated_config = '\n'.join(new_lines)
            else:
                # Add new host entry
                new_entry = f"""
# KVM Host {kvm_host_id} - Database SSH Key
Host {hostname}
    IdentityFile ~/.ssh/{key_filename}
    StrictHostKeyChecking accept-new
    UserKnownHostsFile ~/.ssh/known_hosts
    ServerAliveInterval 60
    ServerAliveCountMax 3
    ConnectTimeout 30
"""
                updated_config = existing_config + new_entry

            # Write updated config
            with open(ssh_config_path, 'w') as f:
                f.write(updated_config)

            os.chmod(ssh_config_path, 0o600)

            logger.info(f"Updated SSH config for host {hostname} to use database key")

            # Update last_used timestamp
            from datetime import datetime
            ssh_key.last_used = datetime.utcnow()
            await db.commit()

            return True

        except Exception as e:
            logger.error(f"Failed to setup SSH key for KVM host {kvm_host_id}: {e}")
            raise

    def _get_connection(
        self,
        uri: str,
        password: Optional[str] = None,
        username: Optional[str] = None
    ) -> libvirt.virConnect:
        """
        Get or create libvirt connection.

        Args:
            uri: libvirt connection URI
            password: Optional password for SASL/TCP authentication
            username: Optional username for authentication

        Returns:
            libvirt connection object
        """
        # Check if we have stored credentials for this URI (unless explicitly provided)
        if password is None and uri in self.auth_credentials:
            password, username = self.auth_credentials[uri]
            logger.debug(f"Using stored credentials for URI: {uri}")

        # Create a unique key for this connection including auth info
        conn_key = uri
        if password:
            # For password-based connections, we'll create a fresh connection each time
            # to avoid caching issues with credentials
            conn_key = f"{uri}:with_password"

        if conn_key not in self.connections:
            try:
                if password:
                    # Use openAuth for password-based authentication
                    logger.info(f"Connecting to libvirt host with password authentication: {uri}")

                    # Extract username from URI if not provided
                    if not username:
                        username = self._extract_username_from_uri(uri)

                    # Create credential callback
                    def _auth_callback(credentials, user_data):
                        """Callback for providing credentials to libvirt."""
                        for credential in credentials:
                            if credential[0] == libvirt.VIR_CRED_AUTHNAME:
                                # Username credential
                                credential[4] = username if username else ""
                            elif credential[0] == libvirt.VIR_CRED_PASSPHRASE:
                                # Password credential
                                credential[4] = password
                            elif credential[0] == libvirt.VIR_CRED_NOECHOPROMPT:
                                # Non-echoed password prompt
                                credential[4] = password
                            else:
                                # Unknown credential type
                                logger.warning(f"Unknown credential type requested: {credential[0]}")
                                return -1
                        return 0

                    # Define which credential types we support
                    auth = [
                        [
                            libvirt.VIR_CRED_AUTHNAME,
                            libvirt.VIR_CRED_PASSPHRASE,
                            libvirt.VIR_CRED_NOECHOPROMPT
                        ],
                        _auth_callback,
                        None
                    ]

                    # Open connection with authentication
                    conn = libvirt.openAuth(uri, auth, 0)
                else:
                    # Use standard open for SSH or other auth methods
                    logger.info(f"Connecting to libvirt host: {uri}")
                    conn = libvirt.open(uri)

                if conn is None:
                    raise Exception(f"Failed to connect to libvirt URI: {uri}")

                self.connections[conn_key] = conn
                logger.info(f"Connected to libvirt host: {uri}")
            except libvirt.libvirtError as e:
                logger.error(f"Failed to connect to libvirt: {e}")
                raise

        return self.connections[conn_key]

    async def test_connection(
        self,
        uri: str,
        password: Optional[str] = None,
        username: Optional[str] = None
    ) -> bool:
        """
        Test connection to KVM host.

        Args:
            uri: libvirt connection URI
            password: Optional password for SASL/TCP authentication
            username: Optional username for authentication

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Create a partial function with the password and username
            def _test_conn():
                return self._get_connection(uri, password, username)

            conn = await self._run_in_executor(_test_conn)
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

    async def check_incremental_support(
        self,
        uri: str,
        vm_uuid: str
    ) -> Dict[str, Any]:
        """
        Check if a VM and its hypervisor support incremental backups.

        This checks:
        1. Libvirt version (requires 6.0+ for checkpoint API)
        2. QEMU version (requires 4.2+ for dirty bitmaps)
        3. VM disk types (RBD requires different handling)
        4. Domain checkpoint capability

        Args:
            uri: Libvirt connection URI
            vm_uuid: UUID of the VM to check

        Returns:
            Dictionary with support status and details:
            - supported: bool - Whether incremental backup is supported
            - reason: str or None - Reason if not supported
            - libvirt_version: int - Libvirt version number
            - qemu_version: tuple or None - QEMU version as (major, minor, patch)
            - disk_info: list - Disk types and their support status
            - recommended_method: str - 'checkpoint', 'qcow2_backing', or 'full_only'

        Related: Issue #15 - Implement Changed Block Tracking (CBT)
        """
        from backend.services.kvm.checkpoint import CheckpointService

        try:
            conn = await self._run_in_executor(self._get_connection, uri)

            def _check_support():
                # Get domain
                domain = conn.lookupByUUIDString(vm_uuid)
                vm_name = domain.name()

                result = {
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "supported": False,
                    "reason": None,
                    "libvirt_version": 0,
                    "qemu_version": None,
                    "disk_info": [],
                    "recommended_method": "full_only"
                }

                # Initialize checkpoint service for version checks
                checkpoint_svc = CheckpointService()
                support_info = checkpoint_svc.check_checkpoint_support(conn, domain)

                result["libvirt_version"] = support_info["libvirt_version"]
                result["qemu_version"] = support_info["qemu_version"]

                # Parse VM XML to get disk information
                xml_desc = domain.XMLDesc(0)
                root = ET.fromstring(xml_desc)

                has_rbd_disks = False
                has_file_disks = False
                all_disks_qcow2 = True

                for disk in root.findall(".//disk[@device='disk']"):
                    disk_type = disk.get("type")
                    source = disk.find("source")
                    target = disk.find("target")
                    driver = disk.find("driver")

                    if target is None:
                        continue

                    target_dev = target.get("dev")
                    disk_info = {
                        "target": target_dev,
                        "type": disk_type,
                        "incremental_capable": False,
                        "method": None
                    }

                    if disk_type == "file":
                        has_file_disks = True
                        disk_format = driver.get("type") if driver is not None else "raw"
                        disk_info["format"] = disk_format

                        if disk_format in ["qcow2", "qed"]:
                            disk_info["incremental_capable"] = True
                            disk_info["method"] = "checkpoint" if support_info["supported"] else "qcow2_backing"
                        else:
                            all_disks_qcow2 = False
                            # Raw file can use checkpoint if supported
                            if support_info["supported"]:
                                disk_info["incremental_capable"] = True
                                disk_info["method"] = "checkpoint"

                    elif disk_type == "network":
                        protocol = source.get("protocol") if source is not None else None
                        if protocol == "rbd":
                            has_rbd_disks = True
                            disk_info["protocol"] = "rbd"
                            disk_info["rbd_name"] = source.get("name") if source is not None else None

                            # RBD requires checkpoint API for incremental
                            if support_info["supported"]:
                                disk_info["incremental_capable"] = True
                                disk_info["method"] = "checkpoint"
                            else:
                                disk_info["incremental_capable"] = False
                                disk_info["reason"] = "RBD disks require libvirt 6.0+ checkpoint API"

                    result["disk_info"].append(disk_info)

                # Determine overall support and recommended method
                all_disks_capable = all(d["incremental_capable"] for d in result["disk_info"])

                if support_info["supported"]:
                    # Full checkpoint API support
                    result["supported"] = True
                    result["recommended_method"] = "checkpoint"
                elif has_file_disks and not has_rbd_disks and all_disks_qcow2:
                    # Fallback to QCOW2 backing file method for file-only setups
                    result["supported"] = True
                    result["recommended_method"] = "qcow2_backing"
                else:
                    result["supported"] = False
                    if has_rbd_disks and not support_info["supported"]:
                        result["reason"] = f"RBD disks require checkpoint API. {support_info.get('reason', 'Libvirt/QEMU version too old')}"
                    elif not all_disks_capable:
                        result["reason"] = "Not all disks support incremental backup"
                    else:
                        result["reason"] = support_info.get("reason", "Unknown")

                return result

            return await self._run_in_executor(_check_support)

        except libvirt.libvirtError as e:
            self._log("ERROR", f"Failed to check incremental support: {e}")
            return {
                "supported": False,
                "reason": str(e),
                "libvirt_version": 0,
                "qemu_version": None,
                "disk_info": [],
                "recommended_method": "full_only"
            }

    async def determine_backup_mode(
        self,
        uri: str,
        vm_uuid: str,
        schedule_policy: str = "auto",
        chain_length: int = 0,
        max_chain_length: int = 14,
        force_full: bool = False
    ) -> Dict[str, Any]:
        """
        Determine whether to perform a full or incremental backup.

        This implements the backup mode decision logic based on:
        - Schedule policy (auto, full_only, incremental_preferred)
        - Current chain length vs maximum
        - Hypervisor capability
        - Force full flag

        Args:
            uri: Libvirt connection URI
            vm_uuid: UUID of the VM
            schedule_policy: Backup mode policy from schedule config
            chain_length: Current number of incrementals in chain
            max_chain_length: Maximum chain length before forcing full
            force_full: Force a full backup regardless of other conditions

        Returns:
            Dictionary with:
            - mode: 'full' or 'incremental'
            - reason: Why this mode was chosen
            - incremental_method: 'checkpoint' or 'qcow2_backing' (if incremental)

        Related: Issue #15 - Implement Changed Block Tracking (CBT)
        """
        result = {
            "mode": "full",
            "reason": None,
            "incremental_method": None
        }

        # Force full always wins
        if force_full:
            result["reason"] = "Full backup requested explicitly"
            return result

        # Full-only policy
        if schedule_policy == "full_only":
            result["reason"] = "Schedule policy requires full backups only"
            return result

        # Check if chain length exceeded
        if chain_length >= max_chain_length:
            result["reason"] = f"Chain length ({chain_length}) reached maximum ({max_chain_length})"
            return result

        # Need to do first backup as full (no parent to reference)
        if chain_length == 0:
            result["reason"] = "First backup in chain must be full"
            return result

        # Check hypervisor capability
        support = await self.check_incremental_support(uri, vm_uuid)

        if not support["supported"]:
            result["reason"] = f"Incremental not supported: {support.get('reason', 'Unknown')}"
            return result

        # All conditions met for incremental
        result["mode"] = "incremental"
        result["incremental_method"] = support["recommended_method"]

        if schedule_policy == "incremental_preferred":
            result["reason"] = "Incremental preferred by policy and supported"
        else:
            result["reason"] = f"Auto mode: chain length {chain_length}/{max_chain_length}, incremental supported"

        return result

    async def create_backup(
        self,
        uri: str,
        vm_uuid: str,
        backup_dir: Path,
        incremental: bool = False,
        parent_backup: Optional[str] = None,
        use_cbt: bool = False,
        ssh_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a backup of a VM.

        Args:
            uri: Libvirt connection URI
            vm_uuid: UUID of the VM to backup
            backup_dir: Directory to store backup files
            incremental: Whether to create incremental backup
            parent_backup: Path to parent backup for incremental
            use_cbt: Whether to use Changed Block Tracking (CBT) for incremental backup (Issue #15)
            ssh_password: Password for SSH authentication to KVM host (for RBD disk exports)

        Returns:
            Dictionary with backup information
        """
        # If CBT is requested for incremental backup, use CBT-based backup
        if use_cbt and incremental:
            return await self._create_cbt_backup(uri, vm_uuid, backup_dir)

        # Otherwise, use traditional backup method
        try:
            conn = await self._run_in_executor(self._get_connection, uri)

            # Capture log method for use in nested function
            log_fn = self._log

            def _backup():
                # Get domain by UUID
                domain = conn.lookupByUUIDString(vm_uuid)
                vm_name = domain.name()

                log_fn("INFO", f"Starting backup of VM: {vm_name} ({vm_uuid})", {
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "operation": "backup_start"
                })

                log_fn("DEBUG", f"Looking up VM by UUID", {"uuid": vm_uuid})

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

                # Log discovered disks
                log_fn("INFO", f"Discovered {len(disks)} disk(s) attached to VM", {
                    "disk_count": len(disks),
                    "disks": [{"target": d.get("target"), "type": d.get("type"), "protocol": d.get("protocol")} for d in disks]
                })

                # Create backup directory
                backup_dir.mkdir(parents=True, exist_ok=True)
                log_fn("DEBUG", f"Created backup directory: {backup_dir}", {"path": str(backup_dir)})

                # Save VM XML configuration
                xml_file = backup_dir / "domain.xml"
                with open(xml_file, 'w') as f:
                    f.write(xml_desc)
                log_fn("INFO", "Saved VM XML configuration to domain.xml", {"file": str(xml_file)})

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

                log_fn("INFO", f"VM state: {self._get_state_name(info[0])}, vCPUs: {info[3]}, Memory: {info[2] // 1024} MB", {
                    "state": self._get_state_name(info[0]),
                    "vcpus": info[3],
                    "memory_mb": info[2] // 1024
                })

                # Save VM info
                info_file = backup_dir / "vm_info.json"
                with open(info_file, 'w') as f:
                    json.dump(vm_info, f, indent=2)
                log_fn("DEBUG", "Saved VM info to vm_info.json", {"file": str(info_file)})

                # Application consistency via guest agent (Issue #14)
                from backend.services.kvm.guest_agent import (
                    GuestAgentService,
                    FreezeStatus,
                    GuestAgentError,
                    GuestAgentTimeout
                )

                application_consistent = False
                fsfreeze_status = FreezeStatus.NOT_ATTEMPTED
                script_log = []

                # Check if VM supports application consistency
                # Note: This requires VM database record to check settings
                # For now, we'll attempt if guest agent is available
                guest_agent = GuestAgentService(domain)
                use_guest_agent = guest_agent.is_guest_agent_available()

                if use_guest_agent:
                    log_fn("INFO", "Guest agent available, attempting application-consistent backup", {
                        "guest_agent": True,
                        "operation": "fsfreeze_attempt"
                    })

                    try:
                        # Execute pre-backup script if configured
                        # TODO: Get script from VM database record
                        # For now, skip script execution (will be added in worker integration)

                        # Freeze filesystem
                        log_fn("DEBUG", "Freezing filesystem via guest agent...", {"timeout": 30})
                        frozen_count = guest_agent.freeze_filesystem(timeout_seconds=30)
                        fsfreeze_status = FreezeStatus.SUCCESS
                        log_fn("INFO", f"Filesystem frozen successfully ({frozen_count} filesystems)", {
                            "frozen_count": frozen_count,
                            "fsfreeze_status": "SUCCESS"
                        })

                        # Update VM info to indicate app consistency
                        vm_info['application_consistent'] = True
                        vm_info['frozen_filesystems'] = frozen_count

                        with open(info_file, 'w') as f:
                            json.dump(vm_info, f, indent=2)

                    except GuestAgentTimeout:
                        log_fn("WARNING", "Filesystem freeze timed out, proceeding with crash-consistent backup", {
                            "fsfreeze_status": "TIMEOUT"
                        })
                        fsfreeze_status = FreezeStatus.TIMEOUT
                        use_guest_agent = False
                    except GuestAgentError as e:
                        log_fn("WARNING", f"Guest agent operation failed: {e}, proceeding with crash-consistent backup", {
                            "error": str(e),
                            "fsfreeze_status": "FAILED"
                        })
                        fsfreeze_status = FreezeStatus.FAILED
                        use_guest_agent = False
                else:
                    log_fn("INFO", "Guest agent not available, creating crash-consistent backup", {
                        "guest_agent": False,
                        "fsfreeze_status": "NOT_AVAILABLE"
                    })
                    fsfreeze_status = FreezeStatus.NOT_AVAILABLE

                # Create snapshot for consistent backup (if VM is running)
                snapshot_name = f"backup-{vm_name}"
                snapshot_created = False

                if info[0] == libvirt.VIR_DOMAIN_RUNNING:
                    log_fn("INFO", "VM is running, creating snapshot for consistent backup", {
                        "snapshot_name": snapshot_name
                    })
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
                        log_fn("INFO", f"Created snapshot for VM: {vm_name}", {
                            "snapshot_name": snapshot_name,
                            "snapshot_created": True
                        })

                        # If filesystem was frozen, we have application-consistent backup
                        if fsfreeze_status == FreezeStatus.SUCCESS:
                            application_consistent = True
                            log_fn("INFO", "Application-consistent backup achieved (filesystem was frozen during snapshot)", {
                                "application_consistent": True
                            })

                    except libvirt.libvirtError as e:
                        log_fn("WARNING", f"Failed to create snapshot (proceeding anyway): {e}", {
                            "error": str(e),
                            "snapshot_created": False
                        })

                    finally:
                        # Always thaw filesystem if it was frozen
                        if use_guest_agent and fsfreeze_status == FreezeStatus.SUCCESS:
                            try:
                                log_fn("DEBUG", "Thawing filesystem...", {})
                                thawed_count = guest_agent.thaw_filesystem()
                                log_fn("INFO", f"Filesystem thawed ({thawed_count} filesystems)", {
                                    "thawed_count": thawed_count
                                })

                                # Execute post-backup script if configured
                                # TODO: Get script from VM database record

                            except Exception as e:
                                log_fn("ERROR", f"Failed to thaw filesystem: {e}", {
                                    "error": str(e),
                                    "critical": True
                                })
                                # This is critical - filesystem is still frozen
                                # Add to script log for visibility
                                script_log.append(f"ERROR: Failed to thaw filesystem: {e}")
                else:
                    # VM not running, no snapshot needed
                    log_fn("INFO", "VM not running, no snapshot needed", {
                        "vm_state": self._get_state_name(info[0])
                    })

                # Backup disk images
                total_size = 0
                backed_up_disks = []

                # Extract hostname from URI for SSH commands
                # Support both qemu+ssh:// and qemu+tcp:// URIs
                import re
                ssh_host = None

                # Try SSH URI first
                ssh_match = re.search(r'ssh://([^@]+@)?([^:/]+)', uri)
                if ssh_match:
                    ssh_user = ssh_match.group(1).rstrip('@') if ssh_match.group(1) else None
                    ssh_hostname = ssh_match.group(2)
                    ssh_host = f"{ssh_user}@{ssh_hostname}" if ssh_user else ssh_hostname
                else:
                    # Try TCP URI - extract hostname and construct SSH connection
                    tcp_match = re.search(r'tcp://([^:/]+)', uri)
                    if tcp_match:
                        ssh_hostname = tcp_match.group(1)
                        # Use root user for TCP connections (default for KVM)
                        ssh_host = f"root@{ssh_hostname}"
                        log_fn("INFO", f"Converted TCP URI to SSH host for disk operations: {ssh_host}", {
                            "ssh_host": ssh_host,
                            "original_uri": uri
                        })

                log_fn("INFO", f"Starting disk backup - {len(disks)} disk(s) to process", {
                    "disk_count": len(disks),
                    "ssh_host": ssh_host
                })

                for disk in disks:
                    disk_type = disk.get("type")
                    target = disk["target"]

                    log_fn("INFO", f"Processing disk: {target} (type: {disk_type})", {
                        "target": target,
                        "disk_type": disk_type,
                        "disk_info": disk
                    })

                    if disk_type == "file":
                        # File-based disk
                        disk_path = Path(disk["path"])

                        # For file-based disks over SSH, we need to copy from remote host
                        if ssh_host:
                            dest_disk = backup_dir / f"{target}.img"
                            log_fn("INFO", f"Copying file-based disk from remote host via SCP: {disk_path}", {
                                "source": str(disk_path),
                                "destination": str(dest_disk),
                                "method": "scp"
                            })

                            import subprocess
                            try:
                                # Use SCP to copy the disk file from remote host
                                cmd = ["scp", f"{ssh_host}:{disk_path}", str(dest_disk)]
                                log_fn("DEBUG", f"Executing SCP command: scp {ssh_host}:{disk_path} {dest_disk}", {
                                    "command": cmd
                                })
                                subprocess.run(cmd, check=True, capture_output=True, text=True)
                                disk_size = dest_disk.stat().st_size
                                log_fn("INFO", f"SCP completed for {target}: {disk_size} bytes ({disk_size / 1024**3:.2f} GB)", {
                                    "target": target,
                                    "size_bytes": disk_size,
                                    "size_gb": round(disk_size / 1024**3, 2)
                                })
                            except subprocess.CalledProcessError as e:
                                log_fn("ERROR", f"SCP failed for {target}: {e.stderr}", {
                                    "target": target,
                                    "error": e.stderr,
                                    "command": cmd
                                })
                                continue
                        else:
                            # Local libvirt - direct file access
                            if not disk_path.exists():
                                log_fn("WARNING", f"Disk not found: {disk_path}", {
                                    "path": str(disk_path)
                                })
                                continue

                            dest_disk = backup_dir / f"{target}.qcow2"

                            # Determine backup method based on incremental flag
                            if incremental and disk_path.suffix in [".qcow2", ".qed"]:
                                log_fn("INFO", f"Creating incremental backup of disk: {target}", {
                                    "target": target,
                                    "method": "qemu-img_incremental"
                                })
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
                                    log_fn("ERROR", f"qemu-img incremental failed for {target}: {e.stderr}, falling back to full copy", {
                                        "target": target,
                                        "error": e.stderr
                                    })
                                    import shutil
                                    shutil.copy2(disk_path, dest_disk)
                            else:
                                # Full backup - copy entire disk image
                                log_fn("INFO", f"Creating full backup of disk: {target} ({disk_path})", {
                                    "target": target,
                                    "source": str(disk_path),
                                    "method": "file_copy"
                                })
                                import shutil
                                shutil.copy2(disk_path, dest_disk)

                            disk_size = dest_disk.stat().st_size
                            log_fn("INFO", f"Local disk backup completed for {target}: {disk_size} bytes", {
                                "target": target,
                                "size_bytes": disk_size
                            })

                    elif disk_type == "network" and disk.get("protocol") == "rbd":
                        # RBD/Ceph disk - export via SSH using qemu-img convert
                        # qemu-img on KVM host can directly access RBD images
                        rbd_pool = disk.get("rbd_pool", "")
                        rbd_image = disk.get("rbd_image", "")
                        rbd_name = disk.get("rbd_name", "")

                        if not ssh_host:
                            log_fn("ERROR", f"RBD backup requires SSH connection, but URI is local: {uri}", {
                                "uri": uri,
                                "rbd_name": rbd_name
                            })
                            continue

                        dest_disk = backup_dir / f"{target}.img"
                        log_fn("INFO", f"Starting RBD disk export: {rbd_name}", {
                            "rbd_name": rbd_name,
                            "rbd_pool": rbd_pool,
                            "rbd_image": rbd_image,
                            "target": target,
                            "destination": str(dest_disk)
                        })

                        import subprocess
                        import uuid
                        try:
                            # Use a two-step approach:
                            # 1. Convert RBD to temp file on KVM host using qemu-img
                            # 2. Stream temp file via SSH and delete it

                            temp_filename = f"/tmp/backup_{uuid.uuid4().hex[:8]}.img"
                            log_fn("INFO", f"Step 1: Converting RBD to temp file on KVM host: {temp_filename}", {
                                "step": 1,
                                "operation": "qemu-img_convert",
                                "source": f"rbd:{rbd_name}",
                                "temp_file": temp_filename,
                                "ssh_host": ssh_host
                            })

                            # Step 1: Convert RBD to file on KVM host
                            # Use sshpass if password is provided
                            if ssh_password:
                                convert_cmd = [
                                    "sshpass", "-p", ssh_password,
                                    "ssh", "-o", "StrictHostKeyChecking=no", ssh_host,
                                    "qemu-img", "convert",
                                    "-O", "raw",
                                    f"rbd:{rbd_name}",
                                    temp_filename
                                ]
                            else:
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

                            log_fn("INFO", f"Step 1 completed: RBD converted to temp file", {
                                "step": 1,
                                "status": "completed",
                                "temp_file": temp_filename
                            })

                            log_fn("INFO", f"Step 2: Streaming temp file to worker and cleaning up", {
                                "step": 2,
                                "operation": "ssh_stream",
                                "source": temp_filename,
                                "destination": str(dest_disk)
                            })

                            # Step 2: Stream file back and delete it
                            # Use && to ensure cleanup happens even if successful
                            if ssh_password:
                                stream_cmd = [
                                    "sshpass", "-p", ssh_password,
                                    "ssh", "-o", "StrictHostKeyChecking=no", ssh_host,
                                    f"cat {temp_filename} && rm -f {temp_filename}"
                                ]
                            else:
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
                            log_fn("INFO", f"RBD export completed for {target}: {disk_size} bytes ({disk_size / 1024**3:.2f} GB)", {
                                "target": target,
                                "rbd_name": rbd_name,
                                "size_bytes": disk_size,
                                "size_gb": round(disk_size / 1024**3, 2),
                                "step": 2,
                                "status": "completed"
                            })

                        except subprocess.CalledProcessError as e:
                            error_msg = e.stderr.decode() if e.stderr else str(e)
                            log_fn("ERROR", f"RBD export failed for {target}: {error_msg}", {
                                "target": target,
                                "rbd_name": rbd_name,
                                "error": error_msg,
                                "error_type": "CalledProcessError"
                            })
                            # Try to clean up temp file
                            try:
                                if ssh_password:
                                    subprocess.run(["sshpass", "-p", ssh_password, "ssh", "-o", "StrictHostKeyChecking=no", ssh_host, f"rm -f {temp_filename}"], timeout=30)
                                else:
                                    subprocess.run(["ssh", ssh_host, f"rm -f {temp_filename}"], timeout=30)
                            except:
                                pass
                            continue
                        except subprocess.TimeoutExpired:
                            log_fn("ERROR", f"RBD export for {target} timed out after 2 hours", {
                                "target": target,
                                "rbd_name": rbd_name,
                                "error_type": "TimeoutExpired",
                                "timeout_seconds": 7200
                            })
                            # Try to clean up temp file
                            try:
                                if ssh_password:
                                    subprocess.run(["sshpass", "-p", ssh_password, "ssh", "-o", "StrictHostKeyChecking=no", ssh_host, f"rm -f {temp_filename}"], timeout=30)
                                else:
                                    subprocess.run(["ssh", ssh_host, f"rm -f {temp_filename}"], timeout=30)
                            except:
                                pass
                            continue
                        except Exception as e:
                            log_fn("ERROR", f"Unexpected error exporting RBD disk {target}: {e}", {
                                "target": target,
                                "rbd_name": rbd_name,
                                "error": str(e),
                                "error_type": type(e).__name__
                            })
                            # Try to clean up temp file
                            try:
                                subprocess.run(["ssh", ssh_host, f"rm -f {temp_filename}"], timeout=30)
                            except:
                                pass
                            continue
                    else:
                        log_fn("WARNING", f"Unsupported disk type: {disk_type} for disk {target}", {
                            "target": target,
                            "disk_type": disk_type
                        })
                        continue

                    total_size += disk_size

                    backed_up_disks.append({
                        "target": target,
                        "file": dest_disk.name,
                        "size": disk_size,
                        "type": disk_type,
                        "incremental": incremental and disk_type == "file" and disk.get("path", "").endswith((".qcow2", ".qed"))
                    })

                    log_fn("INFO", f"Disk backup completed: {target} ({disk_size} bytes)", {
                        "target": target,
                        "size_bytes": disk_size,
                        "disk_type": disk_type
                    })

                # Delete snapshot if created
                if snapshot_created:
                    log_fn("DEBUG", f"Cleaning up snapshot: {snapshot_name}", {"snapshot_name": snapshot_name})
                    try:
                        snapshot = domain.snapshotLookupByName(snapshot_name)
                        snapshot.delete(libvirt.VIR_DOMAIN_SNAPSHOT_DELETE_METADATA_ONLY)
                        log_fn("INFO", f"Deleted snapshot for VM: {vm_name}", {
                            "snapshot_name": snapshot_name,
                            "snapshot_deleted": True
                        })
                    except libvirt.libvirtError as e:
                        log_fn("WARNING", f"Failed to delete snapshot: {e}", {
                            "snapshot_name": snapshot_name,
                            "error": str(e)
                        })

                log_fn("INFO", f"VM backup completed successfully. Total size: {total_size} bytes ({total_size / 1024**3:.2f} GB)", {
                    "vm_name": vm_name,
                    "total_size_bytes": total_size,
                    "total_size_gb": round(total_size / 1024**3, 2),
                    "disk_count": len(backed_up_disks),
                    "application_consistent": application_consistent,
                    "operation": "backup_complete"
                })

                return {
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "state": self._get_state_name(info[0]),
                    "disks": backed_up_disks,
                    "total_size": total_size,
                    "backup_dir": str(backup_dir),
                    "incremental": incremental,
                    # Application consistency metadata (Issue #14)
                    "application_consistent": application_consistent,
                    "fsfreeze_status": fsfreeze_status,
                    "script_execution_log": "\n".join(script_log) if script_log else None
                }

            return await self._run_in_executor(_backup)

        except libvirt.libvirtError as e:
            self._log("ERROR", f"Failed to backup VM: {e}", {
                "error": str(e),
                "error_type": "libvirtError"
            })
            raise
        except Exception as e:
            self._log("ERROR", f"Unexpected error during backup: {e}", {
                "error": str(e),
                "error_type": type(e).__name__
            })
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

        NOTE (Issue #15): CBT incremental restore not yet fully implemented.
        For CBT-based incremental backups, full restore workflow requires:
        1. Query backup chain from database (via BackupChainService)
        2. Download full backup (sequence_number=0) + all incrementals in order
        3. For each incremental: apply changed blocks to disk image
        4. This requires NBD client implementation and disk image manipulation
        Current implementation supports traditional full/incremental restore only.

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

    async def create_incremental_backup(
        self,
        uri: str,
        vm_uuid: str,
        backup_dir: Path,
        parent_checkpoint: Optional[str] = None,
        new_checkpoint_name: Optional[str] = None,
        ssh_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create an incremental backup using libvirt checkpoint API.

        This method uses libvirt's checkpoint API to:
        1. Start a pull-mode backup with NBD exports
        2. Track changed blocks since the parent checkpoint
        3. Export only changed blocks to backup files
        4. Create a new checkpoint for the next incremental

        Args:
            uri: Libvirt connection URI
            vm_uuid: UUID of the VM to backup
            backup_dir: Directory to store backup files
            parent_checkpoint: Name of parent checkpoint (for incremental)
            new_checkpoint_name: Name for the new checkpoint to create
            ssh_password: Password for SSH authentication (for RBD exports)

        Returns:
            Dictionary with backup information including CBT metadata

        Related: Issue #15 - Implement Changed Block Tracking (CBT)
        """
        from backend.services.kvm.checkpoint import CheckpointService, CheckpointError
        import subprocess
        import uuid as uuid_module

        log_fn = self._log
        log_fn("INFO", f"Starting incremental backup of VM {vm_uuid}", {
            "parent_checkpoint": parent_checkpoint,
            "new_checkpoint": new_checkpoint_name,
            "operation": "incremental_backup_start"
        })

        try:
            conn = await self._run_in_executor(self._get_connection, uri)

            def _incremental_backup():
                # Get domain
                domain = conn.lookupByUUIDString(vm_uuid)
                vm_name = domain.name()

                log_fn("INFO", f"Creating incremental backup for VM: {vm_name}", {
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid
                })

                # Initialize checkpoint service
                checkpoint_svc = CheckpointService(log_callback=log_fn)

                # Check checkpoint support
                support = checkpoint_svc.check_checkpoint_support(conn, domain)
                if not support["supported"]:
                    raise CheckpointError(f"Checkpoint not supported: {support.get('reason')}")

                # Get VM XML to find disk targets
                xml_desc = domain.XMLDesc(0)
                root = ET.fromstring(xml_desc)

                disk_targets = []
                disk_info_map = {}

                for disk in root.findall(".//disk[@device='disk']"):
                    target = disk.find("target")
                    source = disk.find("source")
                    driver = disk.find("driver")

                    if target is None:
                        continue

                    target_dev = target.get("dev")
                    disk_targets.append(target_dev)

                    disk_type = disk.get("type")
                    disk_info = {"target": target_dev, "type": disk_type}

                    if disk_type == "network" and source is not None:
                        protocol = source.get("protocol")
                        if protocol == "rbd":
                            disk_info["protocol"] = "rbd"
                            disk_info["rbd_name"] = source.get("name")

                    disk_info_map[target_dev] = disk_info

                if not disk_targets:
                    raise Exception("No disks found for backup")

                log_fn("INFO", f"Found {len(disk_targets)} disk(s) to backup", {
                    "disk_targets": disk_targets
                })

                # Create backup directory and scratch directory
                backup_dir.mkdir(parents=True, exist_ok=True)
                scratch_dir = backup_dir / "scratch"
                scratch_dir.mkdir(parents=True, exist_ok=True)

                # Save VM XML configuration
                xml_file = backup_dir / "domain.xml"
                with open(xml_file, 'w') as f:
                    f.write(xml_desc)

                # Generate checkpoint name if not provided
                if not new_checkpoint_name:
                    new_checkpoint_name_local = f"backup-{vm_name}-{uuid_module.uuid4().hex[:8]}"
                else:
                    new_checkpoint_name_local = new_checkpoint_name

                # Start backup using checkpoint API
                log_fn("INFO", "Starting pull-mode backup via checkpoint API", {
                    "checkpoint_name": new_checkpoint_name_local,
                    "incremental_from": parent_checkpoint
                })

                try:
                    nbd_info = checkpoint_svc.start_backup(
                        domain=domain,
                        disk_targets=disk_targets,
                        scratch_dir=str(scratch_dir),
                        checkpoint_name=new_checkpoint_name_local,
                        incremental_from=parent_checkpoint
                    )

                    log_fn("INFO", "Backup started, NBD exports available", {
                        "nbd_exports": list(nbd_info.keys())
                    })

                    # Export data from NBD to backup files
                    backed_up_disks = []
                    total_size = 0
                    total_changed_blocks = 0

                    for target_dev, nbd in nbd_info.items():
                        socket_path = nbd.get("socket")
                        export_name = nbd.get("export_name", target_dev)

                        if not socket_path:
                            log_fn("WARNING", f"No socket path for disk {target_dev}, skipping")
                            continue

                        # Output file for this disk
                        output_file = backup_dir / f"{target_dev}.qcow2"

                        log_fn("INFO", f"Exporting disk {target_dev} from NBD", {
                            "socket": socket_path,
                            "export": export_name,
                            "output": str(output_file)
                        })

                        # Use qemu-img to export from NBD
                        # For incremental, use -B to reference parent and create thin QCOW2
                        try:
                            if parent_checkpoint:
                                # Incremental backup - create sparse QCOW2 with only changed blocks
                                cmd = [
                                    "qemu-img", "convert",
                                    "-f", "raw",
                                    "-O", "qcow2",
                                    "-c",  # Compress
                                    f"nbd+unix:///{export_name}?socket={socket_path}",
                                    str(output_file)
                                ]
                            else:
                                # Full backup
                                cmd = [
                                    "qemu-img", "convert",
                                    "-f", "raw",
                                    "-O", "qcow2",
                                    "-c",  # Compress
                                    f"nbd+unix:///{export_name}?socket={socket_path}",
                                    str(output_file)
                                ]

                            log_fn("DEBUG", f"Running qemu-img: {' '.join(cmd)}")

                            result = subprocess.run(
                                cmd,
                                capture_output=True,
                                text=True,
                                timeout=7200  # 2 hour timeout
                            )

                            if result.returncode != 0:
                                log_fn("ERROR", f"qemu-img failed for {target_dev}: {result.stderr}")
                                continue

                            disk_size = output_file.stat().st_size
                            total_size += disk_size

                            backed_up_disks.append({
                                "target": target_dev,
                                "file": output_file.name,
                                "size": disk_size,
                                "type": disk_info_map.get(target_dev, {}).get("type", "file"),
                                "incremental": parent_checkpoint is not None
                            })

                            log_fn("INFO", f"Disk {target_dev} exported: {disk_size} bytes", {
                                "target": target_dev,
                                "size_bytes": disk_size,
                                "size_mb": round(disk_size / 1024**2, 2)
                            })

                        except subprocess.TimeoutExpired:
                            log_fn("ERROR", f"qemu-img timed out for {target_dev}")
                            continue
                        except Exception as e:
                            log_fn("ERROR", f"Failed to export {target_dev}: {e}")
                            continue

                finally:
                    # Always stop backup to release NBD exports
                    try:
                        checkpoint_svc.stop_backup(domain)
                        log_fn("INFO", "Backup stopped, NBD exports released")
                    except Exception as e:
                        log_fn("WARNING", f"Error stopping backup: {e}")

                    # Clean up scratch files
                    try:
                        import shutil
                        shutil.rmtree(scratch_dir, ignore_errors=True)
                    except Exception:
                        pass

                # Get VM info
                info = domain.info()
                vm_info = {
                    "name": vm_name,
                    "uuid": vm_uuid,
                    "state": self._get_state_name(info[0]),
                    "vcpus": info[3],
                    "memory": info[2] // 1024,
                    "disks": backed_up_disks,
                    "cbt_enabled": True,
                    "checkpoint_name": new_checkpoint_name_local,
                    "parent_checkpoint": parent_checkpoint,
                    "backup_mode": "incremental" if parent_checkpoint else "full"
                }

                # Save VM info
                info_file = backup_dir / "vm_info.json"
                with open(info_file, 'w') as f:
                    json.dump(vm_info, f, indent=2)

                log_fn("INFO", f"Incremental backup completed. Total size: {total_size} bytes", {
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / 1024**2, 2),
                    "disk_count": len(backed_up_disks),
                    "checkpoint_name": new_checkpoint_name_local,
                    "operation": "incremental_backup_complete"
                })

                return {
                    "vm_name": vm_name,
                    "vm_uuid": vm_uuid,
                    "state": self._get_state_name(info[0]),
                    "disks": backed_up_disks,
                    "total_size": total_size,
                    "backup_dir": str(backup_dir),
                    "incremental": parent_checkpoint is not None,
                    "backup_mode": "incremental" if parent_checkpoint else "full",
                    "cbt_metadata": {
                        "cbt_enabled": True,
                        "checkpoint_name": new_checkpoint_name_local,
                        "parent_checkpoint": parent_checkpoint,
                        "method": "checkpoint"
                    }
                }

            return await self._run_in_executor(_incremental_backup)

        except Exception as e:
            self._log("ERROR", f"Incremental backup failed: {e}", {
                "error": str(e),
                "error_type": type(e).__name__
            })
            raise

    async def _create_cbt_backup(
        self,
        uri: str,
        vm_uuid: str,
        backup_dir: Path
    ) -> Dict[str, Any]:
        """
        Legacy CBT backup method - redirects to create_incremental_backup.

        This method is kept for backward compatibility but now uses the
        new checkpoint-based incremental backup implementation.

        Args:
            uri: Libvirt connection URI
            vm_uuid: UUID of the VM to backup
            backup_dir: Directory to store backup files

        Returns:
            Dictionary with backup information including CBT metadata

        Related: Issue #15 - Implement Changed Block Tracking (CBT)
        """
        # Redirect to new implementation
        return await self.create_incremental_backup(
            uri=uri,
            vm_uuid=vm_uuid,
            backup_dir=backup_dir,
            parent_checkpoint=None,  # First backup in chain
            new_checkpoint_name=None  # Auto-generate
        )

    async def merge_incremental_chain(
        self,
        chain_dirs: List[Path],
        output_dir: Path,
        disk_target: str = "vda"
    ) -> Dict[str, Any]:
        """
        Merge a chain of incremental backups into a single consolidated disk image.

        This function takes the full backup plus all incremental backups in order
        and produces a single QCOW2 image that can be used for VM restoration.

        Args:
            chain_dirs: List of backup directories in order (full first, then incrementals)
            output_dir: Directory to write the merged disk image
            disk_target: Disk target name (e.g., 'vda')

        Returns:
            Dictionary with merge results

        Related: Issue #15 - Implement Changed Block Tracking (CBT)
        """
        import subprocess
        import shutil

        log_fn = self._log
        log_fn("INFO", f"Merging {len(chain_dirs)} backups for disk {disk_target}", {
            "operation": "merge_chain_start",
            "chain_length": len(chain_dirs)
        })

        if not chain_dirs:
            raise ValueError("No backup directories provided for merge")

        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Start with the full backup (first in chain)
            full_backup_dir = chain_dirs[0]
            full_disk_file = full_backup_dir / f"{disk_target}.qcow2"

            if not full_disk_file.exists():
                # Try without extension
                full_disk_file = full_backup_dir / disk_target
                if not full_disk_file.exists():
                    raise FileNotFoundError(f"Full backup disk not found: {disk_target}")

            # Copy full backup as base
            merged_file = output_dir / f"{disk_target}.qcow2"
            log_fn("INFO", f"Copying full backup as merge base", {
                "source": str(full_disk_file),
                "destination": str(merged_file)
            })

            # Use qemu-img convert to create a standalone copy
            result = subprocess.run(
                ["qemu-img", "convert", "-O", "qcow2", str(full_disk_file), str(merged_file)],
                capture_output=True,
                text=True,
                timeout=7200
            )

            if result.returncode != 0:
                raise Exception(f"Failed to copy full backup: {result.stderr}")

            # Apply each incremental in order
            for i, incr_dir in enumerate(chain_dirs[1:], start=1):
                incr_disk_file = incr_dir / f"{disk_target}.qcow2"

                if not incr_disk_file.exists():
                    log_fn("WARNING", f"Incremental disk not found, skipping: {incr_disk_file}")
                    continue

                log_fn("INFO", f"Applying incremental {i}/{len(chain_dirs)-1}", {
                    "source": str(incr_disk_file),
                    "target": str(merged_file)
                })

                # Rebase the incremental to point to our merged file, then commit
                # First, create a temporary copy that references our merged file
                temp_file = output_dir / f"temp_merge_{i}.qcow2"

                # Create overlay on merged file
                result = subprocess.run(
                    ["qemu-img", "create", "-f", "qcow2", "-b", str(merged_file),
                     "-F", "qcow2", str(temp_file)],
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if result.returncode != 0:
                    raise Exception(f"Failed to create overlay: {result.stderr}")

                # Copy incremental changes to the overlay
                # Use qemu-img convert with the incremental as source
                result = subprocess.run(
                    ["qemu-img", "convert", "-O", "qcow2", "-B", str(merged_file),
                     str(incr_disk_file), str(temp_file)],
                    capture_output=True,
                    text=True,
                    timeout=7200
                )

                # If convert failed, try an alternative approach - commit changes
                if result.returncode != 0:
                    log_fn("DEBUG", f"Direct convert failed, trying rebase approach")

                    # Alternative: copy incremental and rebase
                    temp_incr = output_dir / f"temp_incr_{i}.qcow2"
                    shutil.copy2(incr_disk_file, temp_incr)

                    # Rebase to our merged file
                    result = subprocess.run(
                        ["qemu-img", "rebase", "-f", "qcow2", "-b", str(merged_file),
                         "-F", "qcow2", "-u", str(temp_incr)],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )

                    if result.returncode == 0:
                        # Commit the changes
                        result = subprocess.run(
                            ["qemu-img", "commit", "-f", "qcow2", str(temp_incr)],
                            capture_output=True,
                            text=True,
                            timeout=7200
                        )

                    # Clean up temporary file
                    if temp_incr.exists():
                        temp_incr.unlink()

                # Clean up temporary overlay
                if temp_file.exists():
                    temp_file.unlink()

            # Get final merged file info
            result = subprocess.run(
                ["qemu-img", "info", "--output=json", str(merged_file)],
                capture_output=True,
                text=True
            )

            merged_size = merged_file.stat().st_size

            log_fn("INFO", f"Chain merge completed", {
                "operation": "merge_chain_complete",
                "output_file": str(merged_file),
                "merged_size": merged_size
            })

            return {
                "success": True,
                "merged_file": str(merged_file),
                "merged_size": merged_size,
                "chain_length": len(chain_dirs),
                "disk_target": disk_target
            }

        except subprocess.TimeoutExpired:
            log_fn("ERROR", "Merge operation timed out")
            raise Exception("Merge operation timed out")
        except Exception as e:
            log_fn("ERROR", f"Chain merge failed: {e}")
            raise

    async def restore_from_chain(
        self,
        uri: str,
        chain_backup_dirs: List[Path],
        new_name: Optional[str] = None,
        overwrite: bool = False,
        storage_type: str = "auto",
        storage_config: Optional[dict] = None,
        host_config: Optional[dict] = None
    ) -> Dict[str, Any]:
        """
        Restore a VM from a chain of incremental backups.

        This method:
        1. Merges all incremental backups into a single disk image
        2. Restores the VM using the merged image

        Args:
            uri: Libvirt connection URI
            chain_backup_dirs: List of backup directories (full first, then incrementals)
            new_name: Optional new name for the restored VM
            overwrite: Whether to overwrite existing VM
            storage_type: Storage type: "auto", "file", or "rbd"
            storage_config: Optional storage configuration override
            host_config: KVM host configuration

        Returns:
            Dictionary with restore results

        Related: Issue #15 - Implement Changed Block Tracking (CBT)
        """
        import tempfile

        log_fn = self._log
        log_fn("INFO", f"Starting chain restore with {len(chain_backup_dirs)} backups", {
            "operation": "chain_restore_start",
            "chain_length": len(chain_backup_dirs),
            "new_name": new_name
        })

        if not chain_backup_dirs:
            raise ValueError("No backup directories provided for restore")

        # Get VM info from the first (full) backup
        full_backup_dir = chain_backup_dirs[0]
        info_file = full_backup_dir / "vm_info.json"

        if not info_file.exists():
            raise FileNotFoundError("vm_info.json not found in full backup")

        with open(info_file, 'r') as f:
            vm_info = json.load(f)

        # Get disk targets to merge
        disk_targets = [d.get("target") for d in vm_info.get("disks", [{"target": "vda"}])]
        if not disk_targets:
            disk_targets = ["vda"]

        # Create temp directory for merged images
        with tempfile.TemporaryDirectory() as temp_dir:
            merged_dir = Path(temp_dir) / "merged"
            merged_dir.mkdir()

            # Merge each disk
            for disk_target in disk_targets:
                try:
                    merge_result = await self.merge_incremental_chain(
                        chain_dirs=chain_backup_dirs,
                        output_dir=merged_dir,
                        disk_target=disk_target
                    )
                    log_fn("INFO", f"Merged disk {disk_target}", {
                        "size": merge_result.get("merged_size")
                    })
                except FileNotFoundError:
                    log_fn("WARNING", f"Disk {disk_target} not found in chain, skipping")
                    continue

            # Copy domain.xml from the most recent backup (last in chain)
            # as it may have more recent configuration
            latest_backup_dir = chain_backup_dirs[-1]
            domain_xml_src = latest_backup_dir / "domain.xml"
            if not domain_xml_src.exists():
                domain_xml_src = full_backup_dir / "domain.xml"

            if domain_xml_src.exists():
                import shutil
                shutil.copy2(domain_xml_src, merged_dir / "domain.xml")

            # Copy vm_info.json
            import shutil
            shutil.copy2(info_file, merged_dir / "vm_info.json")

            # Now restore from the merged directory using the standard restore method
            restore_result = await self.restore_vm(
                uri=uri,
                backup_dir=merged_dir,
                new_name=new_name,
                overwrite=overwrite,
                storage_type=storage_type,
                storage_config=storage_config,
                host_config=host_config
            )

            log_fn("INFO", f"Chain restore completed", {
                "operation": "chain_restore_complete",
                "vm_name": restore_result.get("vm_name"),
                "chain_length": len(chain_backup_dirs)
            })

            return {
                **restore_result,
                "chain_restore": True,
                "chain_length": len(chain_backup_dirs)
            }

    def close_connections(self):
        """Close all libvirt connections."""
        for uri, conn in self.connections.items():
            try:
                conn.close()
                logger.info(f"Closed connection to: {uri}")
            except Exception as e:
                logger.error(f"Error closing connection to {uri}: {e}")

        self.connections.clear()
