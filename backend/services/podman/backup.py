"""
Podman container backup service.
"""
import asyncio
import json
import tarfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import logging

try:
    from podman import PodmanClient
    PODMAN_AVAILABLE = True
except ImportError:
    PODMAN_AVAILABLE = False
    logging.warning("Podman Python library not available")

logger = logging.getLogger(__name__)


class PodmanBackupService:
    """Service for backing up Podman containers."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.clients: Dict[str, 'PodmanClient'] = {}

    async def _run_in_executor(self, func, *args):
        """Run blocking Podman call in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args)

    def _get_client(self, uri: str) -> 'PodmanClient':
        """Get or create Podman client."""
        if not PODMAN_AVAILABLE:
            raise Exception("Podman Python library not available")

        if uri not in self.clients:
            try:
                # Parse URI to get socket path
                # Format: unix:///run/podman/podman.sock or tcp://host:port
                client = PodmanClient(base_url=uri)
                # Test connection
                client.ping()
                self.clients[uri] = client
                logger.info(f"Connected to Podman host: {uri}")
            except Exception as e:
                logger.error(f"Failed to connect to Podman: {e}")
                raise

        return self.clients[uri]

    async def test_connection(self, uri: str) -> bool:
        """Test connection to Podman host."""
        try:
            client = await self._run_in_executor(self._get_client, uri)
            await self._run_in_executor(client.ping)
            return True
        except Exception as e:
            logger.error(f"Podman connection test failed: {e}")
            return False

    async def list_containers(
        self,
        uri: str,
        all_containers: bool = True
    ) -> List[Dict[str, Any]]:
        """List all containers on a Podman host."""
        try:
            client = await self._run_in_executor(self._get_client, uri)

            def _list():
                containers = client.containers.list(all=all_containers)
                result = []
                for container in containers:
                    result.append({
                        "id": container.id,
                        "name": container.name,
                        "image": container.image.tags[0] if container.image.tags else container.image.id,
                        "state": container.status,
                        "created": container.attrs.get("Created"),
                    })
                return result

            return await self._run_in_executor(_list)

        except Exception as e:
            logger.error(f"Failed to list containers: {e}")
            raise

    async def create_backup(
        self,
        uri: str,
        container_id: str,
        backup_dir: Path,
        include_volumes: bool = True
    ) -> Dict[str, Any]:
        """
        Create a backup of a container.

        Args:
            uri: Podman connection URI
            container_id: ID or name of the container
            backup_dir: Directory to store backup files
            include_volumes: Whether to backup volumes

        Returns:
            Dictionary with backup information
        """
        try:
            client = await self._run_in_executor(self._get_client, uri)

            def _backup():
                # Get container
                container = client.containers.get(container_id)
                container_name = container.name

                logger.info(f"Starting backup of container: {container_name} ({container_id})")

                # Create backup directory
                backup_dir.mkdir(parents=True, exist_ok=True)

                # Get container configuration
                container_config = container.attrs

                # Save container config
                config_file = backup_dir / "container_config.json"
                with open(config_file, 'w') as f:
                    json.dump(container_config, f, indent=2)

                # Export container filesystem
                logger.info(f"Exporting container filesystem: {container_name}")
                export_file = backup_dir / "filesystem.tar"

                with open(export_file, 'wb') as f:
                    for chunk in container.export():
                        f.write(chunk)

                export_size = export_file.stat().st_size
                logger.info(f"Exported filesystem: {export_size} bytes")

                # Get image information
                image_info = {
                    "id": container.image.id,
                    "tags": container.image.tags,
                }

                # Save image info
                image_file = backup_dir / "image_info.json"
                with open(image_file, 'w') as f:
                    json.dump(image_info, f, indent=2)

                # Backup volumes if requested
                volumes_backed_up = []
                volumes_size = 0

                if include_volumes:
                    mounts = container_config.get("Mounts", [])
                    for mount in mounts:
                        if mount.get("Type") == "volume":
                            volume_name = mount.get("Name")
                            if volume_name:
                                logger.info(f"Backing up volume: {volume_name}")

                                try:
                                    volume = client.volumes.get(volume_name)
                                    volume_path = Path(volume.attrs.get("Mountpoint", ""))

                                    if volume_path.exists():
                                        # Create volume backup archive
                                        volume_backup = backup_dir / f"volume_{volume_name}.tar"
                                        with tarfile.open(volume_backup, 'w') as tar:
                                            tar.add(volume_path, arcname=volume_name)

                                        volume_size = volume_backup.stat().st_size
                                        volumes_size += volume_size

                                        volumes_backed_up.append({
                                            "name": volume_name,
                                            "destination": mount.get("Destination"),
                                            "size": volume_size
                                        })

                                        logger.info(f"Backed up volume: {volume_name} ({volume_size} bytes)")
                                except Exception as e:
                                    logger.error(f"Failed to backup volume {volume_name}: {e}")

                # Create checkpoint (if container is running)
                checkpoint_created = False
                if container.status == "running":
                    try:
                        logger.info(f"Creating checkpoint for container: {container_name}")
                        # Note: Checkpoint API may vary by Podman version
                        # This is a placeholder for checkpoint functionality
                        # container.checkpoint(name="backup-checkpoint")
                        # checkpoint_created = True
                        logger.info("Checkpoint support is limited in Python Podman API")
                    except Exception as e:
                        logger.warning(f"Failed to create checkpoint: {e}")

                total_size = export_size + volumes_size

                return {
                    "container_name": container_name,
                    "container_id": container_id,
                    "state": container.status,
                    "image": image_info,
                    "filesystem_size": export_size,
                    "volumes": volumes_backed_up,
                    "volumes_size": volumes_size,
                    "total_size": total_size,
                    "backup_dir": str(backup_dir),
                    "checkpoint_created": checkpoint_created
                }

            return await self._run_in_executor(_backup)

        except Exception as e:
            logger.error(f"Failed to backup container: {e}")
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

    async def get_container_info(
        self,
        uri: str,
        container_id: str
    ) -> Dict[str, Any]:
        """Get detailed information about a container."""
        try:
            client = await self._run_in_executor(self._get_client, uri)

            def _get_info():
                container = client.containers.get(container_id)
                config = container.attrs

                # Calculate total size (image + writable layer)
                size_info = container.stats(stream=False) if hasattr(container, 'stats') else {}

                # Get volume information
                volumes = []
                mounts = config.get("Mounts", [])
                for mount in mounts:
                    if mount.get("Type") == "volume":
                        volumes.append({
                            "name": mount.get("Name"),
                            "destination": mount.get("Destination"),
                            "mode": mount.get("Mode")
                        })

                return {
                    "id": container.id,
                    "name": container.name,
                    "image": container.image.tags[0] if container.image.tags else container.image.id,
                    "image_id": container.image.id,
                    "state": container.status,
                    "created": config.get("Created"),
                    "volumes": volumes,
                    "size_info": size_info
                }

            return await self._run_in_executor(_get_info)

        except Exception as e:
            logger.error(f"Failed to get container info: {e}")
            raise

    def close_connections(self):
        """Close all Podman client connections."""
        for uri, client in self.clients.items():
            try:
                client.close()
                logger.info(f"Closed connection to: {uri}")
            except Exception as e:
                logger.error(f"Error closing connection to {uri}: {e}")

        self.clients.clear()
