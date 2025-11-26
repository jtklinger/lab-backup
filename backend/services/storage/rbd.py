"""
RBD (RADOS Block Device) backup service for Ceph-backed VM disks.

This service provides RBD-native incremental backup capabilities using
Ceph's snapshot and export-diff features, which only transfer changed
blocks between snapshots.
"""
import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.core.config import settings

logger = logging.getLogger(__name__)


class RBDError(Exception):
    """Base exception for RBD operations."""
    pass


class RBDConnectionError(RBDError):
    """Exception raised when connection to Ceph cluster fails."""
    pass


class RBDSnapshotError(RBDError):
    """Exception raised when snapshot operations fail."""
    pass


class RBDExportError(RBDError):
    """Exception raised when export operations fail."""
    pass


class RBDBackupService:
    """
    Service for RBD-native backup operations.

    Uses Ceph's native snapshot and export-diff capabilities for
    efficient incremental backups of RBD-backed VM disks.
    """

    def __init__(
        self,
        ceph_conf: Optional[str] = None,
        ceph_user: Optional[str] = None,
        keyring_path: Optional[str] = None
    ):
        """
        Initialize RBD backup service.

        Args:
            ceph_conf: Path to ceph.conf (default from settings)
            ceph_user: Ceph user for authentication (default from settings)
            keyring_path: Path to keyring file (default from settings)
        """
        self.ceph_conf = ceph_conf or settings.CEPH_CONF_PATH
        self.ceph_user = ceph_user or settings.CEPH_USER
        self.keyring_path = keyring_path or settings.CEPH_KEYRING_PATH
        self._connected = False

    def _build_rbd_command(self, *args: str) -> List[str]:
        """Build RBD command with authentication arguments."""
        cmd = ["rbd"]

        if self.ceph_conf:
            cmd.extend(["--conf", self.ceph_conf])

        if self.ceph_user:
            cmd.extend(["--id", self.ceph_user])

        if self.keyring_path:
            cmd.extend(["--keyring", self.keyring_path])

        cmd.extend(args)
        return cmd

    async def _run_command(
        self,
        cmd: List[str],
        check: bool = True,
        capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a command asynchronously."""
        logger.debug(f"Running RBD command: {' '.join(cmd)}")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=False
            )
        )

        if check and result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else f"Command failed with code {result.returncode}"
            raise RBDError(f"RBD command failed: {error_msg}")

        return result

    async def _run_ssh_command(
        self,
        ssh_host: str,
        cmd: List[str],
        check: bool = True,
        ssh_password: Optional[str] = None
    ) -> subprocess.CompletedProcess:
        """Run a command on remote host via SSH."""
        if ssh_password:
            # Use sshpass for password authentication
            ssh_cmd = [
                "sshpass", "-p", ssh_password,
                "ssh", "-o", "StrictHostKeyChecking=no", ssh_host
            ] + cmd
        else:
            # Use key-based authentication
            ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", ssh_host] + cmd
        return await self._run_command(ssh_cmd, check=check)

    async def test_connection(
        self,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None
    ) -> bool:
        """
        Test connection to Ceph cluster.

        Args:
            ssh_host: If provided, test connection via SSH to this host
            ssh_password: Password for SSH authentication

        Returns:
            True if connection successful
        """
        try:
            cmd = self._build_rbd_command("pool", "ls")

            if ssh_host:
                result = await self._run_ssh_command(ssh_host, cmd, check=False, ssh_password=ssh_password)
            else:
                result = await self._run_command(cmd, check=False)

            if result.returncode == 0:
                self._connected = True
                return True

            logger.error(f"Ceph connection test failed: {result.stderr}")
            return False

        except Exception as e:
            logger.error(f"Failed to connect to Ceph cluster: {e}")
            return False

    async def get_image_info(
        self,
        pool: str,
        image: str,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get information about an RBD image.

        Args:
            pool: Ceph pool name
            image: RBD image name
            ssh_host: Run command via SSH on this host
            ssh_password: Password for SSH authentication

        Returns:
            Dictionary with image information (size, features, etc.)
        """
        cmd = self._build_rbd_command("info", f"{pool}/{image}", "--format", "json")

        if ssh_host:
            result = await self._run_ssh_command(ssh_host, cmd, ssh_password=ssh_password)
        else:
            result = await self._run_command(cmd)

        import json
        return json.loads(result.stdout)

    async def check_features(
        self,
        pool: str,
        image: str,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Check if RBD image has features required for efficient incremental backups.

        Args:
            pool: Ceph pool name
            image: RBD image name
            ssh_host: Run command via SSH on this host
            ssh_password: Password for SSH authentication

        Returns:
            Dictionary with feature availability:
            - fast_diff: True if fast-diff feature is enabled
            - object_map: True if object-map feature is enabled
            - incremental_capable: True if both required features are present
        """
        try:
            info = await self.get_image_info(pool, image, ssh_host, ssh_password)
            features = info.get("features", [])

            # Features can be a list of strings or a single string
            if isinstance(features, str):
                features = [features]

            has_fast_diff = "fast-diff" in features
            has_object_map = "object-map" in features

            result = {
                "fast_diff": has_fast_diff,
                "object_map": has_object_map,
                "incremental_capable": has_fast_diff and has_object_map,
                "all_features": features
            }

            if not result["incremental_capable"] and settings.CEPH_RBD_FEATURES_CHECK:
                missing = []
                if not has_fast_diff:
                    missing.append("fast-diff")
                if not has_object_map:
                    missing.append("object-map")
                logger.warning(
                    f"RBD image {pool}/{image} missing features for optimal incremental: {missing}. "
                    f"Enable with: rbd feature enable {pool}/{image} {' '.join(missing)}"
                )

            return result

        except Exception as e:
            logger.error(f"Failed to check RBD features for {pool}/{image}: {e}")
            return {
                "fast_diff": False,
                "object_map": False,
                "incremental_capable": False,
                "error": str(e)
            }

    async def list_snapshots(
        self,
        pool: str,
        image: str,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all snapshots for an RBD image.

        Args:
            pool: Ceph pool name
            image: RBD image name
            ssh_host: Run command via SSH on this host
            ssh_password: Password for SSH authentication

        Returns:
            List of snapshot information dictionaries
        """
        cmd = self._build_rbd_command("snap", "ls", f"{pool}/{image}", "--format", "json")

        if ssh_host:
            result = await self._run_ssh_command(ssh_host, cmd, ssh_password=ssh_password)
        else:
            result = await self._run_command(cmd)

        import json
        snapshots = json.loads(result.stdout) if result.stdout.strip() else []
        return snapshots

    async def create_snapshot(
        self,
        pool: str,
        image: str,
        snap_name: Optional[str] = None,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None
    ) -> str:
        """
        Create an RBD snapshot.

        Args:
            pool: Ceph pool name
            image: RBD image name
            snap_name: Snapshot name (auto-generated if not provided)
            ssh_host: Run command via SSH on this host
            ssh_password: Password for SSH authentication

        Returns:
            Full snapshot specification (pool/image@snap_name)
        """
        if snap_name is None:
            snap_name = f"backup-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

        snap_spec = f"{pool}/{image}@{snap_name}"
        cmd = self._build_rbd_command("snap", "create", snap_spec)

        logger.info(f"Creating RBD snapshot: {snap_spec}")

        try:
            if ssh_host:
                await self._run_ssh_command(ssh_host, cmd, ssh_password=ssh_password)
            else:
                await self._run_command(cmd)

            logger.info(f"Created RBD snapshot: {snap_spec}")
            return snap_spec

        except Exception as e:
            raise RBDSnapshotError(f"Failed to create snapshot {snap_spec}: {e}")

    async def delete_snapshot(
        self,
        pool: str,
        image: str,
        snap_name: str,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None
    ) -> bool:
        """
        Delete an RBD snapshot.

        Args:
            pool: Ceph pool name
            image: RBD image name
            snap_name: Snapshot name to delete
            ssh_host: Run command via SSH on this host
            ssh_password: Password for SSH authentication

        Returns:
            True if deletion successful
        """
        snap_spec = f"{pool}/{image}@{snap_name}"
        cmd = self._build_rbd_command("snap", "rm", snap_spec)

        logger.info(f"Deleting RBD snapshot: {snap_spec}")

        try:
            if ssh_host:
                await self._run_ssh_command(ssh_host, cmd, ssh_password=ssh_password)
            else:
                await self._run_command(cmd)

            logger.info(f"Deleted RBD snapshot: {snap_spec}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete snapshot {snap_spec}: {e}")
            return False

    async def export_full(
        self,
        pool: str,
        image: str,
        snap_name: str,
        output_path: Path,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Export full RBD image from snapshot.

        Args:
            pool: Ceph pool name
            image: RBD image name
            snap_name: Snapshot to export from
            output_path: Local path to write export to
            ssh_host: Run export on remote host and stream to local
            ssh_password: Password for SSH authentication
            progress_callback: Optional callback(bytes_written, total_bytes)

        Returns:
            Dictionary with export information (size, duration, etc.)
        """
        snap_spec = f"{pool}/{image}@{snap_name}"

        logger.info(f"Starting full RBD export: {snap_spec} -> {output_path}")
        start_time = datetime.utcnow()

        try:
            if ssh_host:
                # Export on remote host, pipe to local file
                # Use rbd export with - for stdout, pipe through SSH
                remote_cmd = self._build_rbd_command("export", snap_spec, "-")
                if ssh_password:
                    ssh_cmd = ["sshpass", "-p", ssh_password, "ssh", "-o", "StrictHostKeyChecking=no", ssh_host] + remote_cmd
                else:
                    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", ssh_host] + remote_cmd

                with open(output_path, "wb") as f:
                    process = await asyncio.create_subprocess_exec(
                        *ssh_cmd,
                        stdout=f,
                        stderr=asyncio.subprocess.PIPE
                    )
                    _, stderr = await process.communicate()

                    if process.returncode != 0:
                        raise RBDExportError(f"RBD export failed: {stderr.decode()}")
            else:
                # Local export
                cmd = self._build_rbd_command("export", snap_spec, str(output_path))
                await self._run_command(cmd)

            # Get exported file size
            file_size = output_path.stat().st_size
            duration = (datetime.utcnow() - start_time).total_seconds()

            result = {
                "success": True,
                "export_type": "full",
                "snapshot": snap_spec,
                "output_path": str(output_path),
                "size_bytes": file_size,
                "duration_seconds": duration,
                "throughput_mbps": (file_size / 1024 / 1024) / duration if duration > 0 else 0
            }

            logger.info(
                f"Completed full RBD export: {file_size / 1024 / 1024:.2f} MB "
                f"in {duration:.1f}s ({result['throughput_mbps']:.1f} MB/s)"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to export {snap_spec}: {e}")
            raise RBDExportError(f"Failed to export {snap_spec}: {e}")

    async def export_diff(
        self,
        pool: str,
        image: str,
        from_snap: str,
        to_snap: str,
        output_path: Path,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Export only changed blocks between two snapshots (incremental).

        This uses RBD's native differential export which only transfers
        blocks that have changed between the two snapshots.

        Args:
            pool: Ceph pool name
            image: RBD image name
            from_snap: Base snapshot name (previous backup)
            to_snap: Target snapshot name (current backup)
            output_path: Local path to write diff export to
            ssh_host: Run export on remote host and stream to local
            ssh_password: Password for SSH authentication
            progress_callback: Optional callback(bytes_written, total_bytes)

        Returns:
            Dictionary with export information (diff_size, duration, etc.)
        """
        from_spec = f"{pool}/{image}@{from_snap}"
        to_spec = f"{pool}/{image}@{to_snap}"

        logger.info(f"Starting incremental RBD export: {from_spec} -> {to_spec} to {output_path}")
        start_time = datetime.utcnow()

        try:
            if ssh_host:
                # Export diff on remote host, pipe to local file
                remote_cmd = self._build_rbd_command(
                    "export-diff", "--from-snap", from_snap, to_spec, "-"
                )
                if ssh_password:
                    ssh_cmd = ["sshpass", "-p", ssh_password, "ssh", "-o", "StrictHostKeyChecking=no", ssh_host] + remote_cmd
                else:
                    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", ssh_host] + remote_cmd

                with open(output_path, "wb") as f:
                    process = await asyncio.create_subprocess_exec(
                        *ssh_cmd,
                        stdout=f,
                        stderr=asyncio.subprocess.PIPE
                    )
                    _, stderr = await process.communicate()

                    if process.returncode != 0:
                        raise RBDExportError(f"RBD export-diff failed: {stderr.decode()}")
            else:
                # Local export-diff
                cmd = self._build_rbd_command(
                    "export-diff", "--from-snap", from_snap, to_spec, str(output_path)
                )
                await self._run_command(cmd)

            # Get exported file size
            file_size = output_path.stat().st_size
            duration = (datetime.utcnow() - start_time).total_seconds()

            result = {
                "success": True,
                "export_type": "incremental",
                "from_snapshot": from_spec,
                "to_snapshot": to_spec,
                "output_path": str(output_path),
                "diff_size_bytes": file_size,
                "duration_seconds": duration,
                "throughput_mbps": (file_size / 1024 / 1024) / duration if duration > 0 else 0
            }

            logger.info(
                f"Completed incremental RBD export: {file_size / 1024 / 1024:.2f} MB diff "
                f"in {duration:.1f}s ({result['throughput_mbps']:.1f} MB/s)"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to export diff from {from_spec} to {to_spec}: {e}")
            raise RBDExportError(f"Failed to export diff: {e}")

    async def import_full(
        self,
        input_path: Path,
        pool: str,
        image: str,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Import full RBD image from backup file.

        Args:
            input_path: Path to backup file
            pool: Target Ceph pool
            image: Target RBD image name
            ssh_host: Run import on remote host
            ssh_password: Password for SSH authentication

        Returns:
            Dictionary with import information
        """
        target_spec = f"{pool}/{image}"

        logger.info(f"Starting full RBD import: {input_path} -> {target_spec}")
        start_time = datetime.utcnow()

        try:
            if ssh_host:
                # Stream local file to remote rbd import
                cmd = self._build_rbd_command("import", "-", target_spec)
                if ssh_password:
                    ssh_cmd = ["sshpass", "-p", ssh_password, "ssh", "-o", "StrictHostKeyChecking=no", ssh_host] + cmd
                else:
                    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", ssh_host] + cmd

                with open(input_path, "rb") as f:
                    process = await asyncio.create_subprocess_exec(
                        *ssh_cmd,
                        stdin=f,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        raise RBDError(f"RBD import failed: {stderr.decode()}")
            else:
                cmd = self._build_rbd_command("import", str(input_path), target_spec)
                await self._run_command(cmd)

            duration = (datetime.utcnow() - start_time).total_seconds()
            file_size = input_path.stat().st_size

            return {
                "success": True,
                "import_type": "full",
                "source_path": str(input_path),
                "target_image": target_spec,
                "size_bytes": file_size,
                "duration_seconds": duration
            }

        except Exception as e:
            logger.error(f"Failed to import {input_path} to {target_spec}: {e}")
            raise RBDError(f"Failed to import: {e}")

    async def import_diff(
        self,
        input_path: Path,
        pool: str,
        image: str,
        ssh_host: Optional[str] = None,
        ssh_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Apply incremental diff to existing RBD image.

        Args:
            input_path: Path to diff backup file
            pool: Target Ceph pool
            image: Target RBD image name (must already exist)
            ssh_host: Run import on remote host
            ssh_password: Password for SSH authentication

        Returns:
            Dictionary with import information
        """
        target_spec = f"{pool}/{image}"

        logger.info(f"Starting diff RBD import: {input_path} -> {target_spec}")
        start_time = datetime.utcnow()

        try:
            if ssh_host:
                # Stream local diff to remote rbd import-diff
                cmd = self._build_rbd_command("import-diff", "-", target_spec)
                if ssh_password:
                    ssh_cmd = ["sshpass", "-p", ssh_password, "ssh", "-o", "StrictHostKeyChecking=no", ssh_host] + cmd
                else:
                    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", ssh_host] + cmd

                with open(input_path, "rb") as f:
                    process = await asyncio.create_subprocess_exec(
                        *ssh_cmd,
                        stdin=f,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        raise RBDError(f"RBD import-diff failed: {stderr.decode()}")
            else:
                cmd = self._build_rbd_command("import-diff", str(input_path), target_spec)
                await self._run_command(cmd)

            duration = (datetime.utcnow() - start_time).total_seconds()
            file_size = input_path.stat().st_size

            return {
                "success": True,
                "import_type": "incremental",
                "source_path": str(input_path),
                "target_image": target_spec,
                "diff_size_bytes": file_size,
                "duration_seconds": duration
            }

        except Exception as e:
            logger.error(f"Failed to import diff {input_path} to {target_spec}: {e}")
            raise RBDError(f"Failed to import diff: {e}")

    @staticmethod
    def parse_rbd_source(source: str) -> Dict[str, str]:
        """
        Parse RBD source string from libvirt disk definition.

        Args:
            source: RBD source string (e.g., "pool/image" or "rbd:pool/image")

        Returns:
            Dictionary with 'pool' and 'image' keys
        """
        # Remove rbd: prefix if present
        if source.startswith("rbd:"):
            source = source[4:]

        # Handle any snapshot reference
        if "@" in source:
            source = source.split("@")[0]

        # Split pool/image
        if "/" in source:
            pool, image = source.split("/", 1)
        else:
            pool = "rbd"  # Default pool
            image = source

        return {"pool": pool, "image": image}

    @staticmethod
    def generate_snapshot_name(prefix: str = "backup") -> str:
        """Generate a unique snapshot name based on current timestamp."""
        return f"{prefix}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
