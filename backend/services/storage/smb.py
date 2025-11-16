"""
SMB/CIFS storage backend implementation.
"""
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, BinaryIO
import hashlib
import io

from smbclient import open_file, listdir, scandir, stat, remove, mkdir
from smbclient.path import exists as smb_exists
import smbclient

from backend.services.storage.base import (
    StorageBackend,
    StorageError,
    StorageConnectionError,
    StorageUploadError,
    StorageDownloadError,
    StorageNotFoundError,
)


class SMBStorage(StorageBackend):
    """SMB/CIFS network storage backend."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize SMB storage backend.

        Config format:
        {
            "server": "192.168.1.100",
            "share": "backups",
            "username": "backup_user",
            "password": "password",
            "domain": "WORKGROUP",  # optional
            "path": "/",  # optional base path within share
            "port": 445  # optional, defaults to 445
        }
        """
        super().__init__(config)

        self.server = config.get("server")
        self.share = config.get("share")
        self.username = config.get("username")
        self.password = config.get("password")
        self.domain = config.get("domain", "")
        self.base_path = config.get("path", "/").strip("/")
        self.port = config.get("port", 445)

        if not all([self.server, self.share, self.username, self.password]):
            raise StorageError("SMB configuration requires server, share, username, and password")

        # Register SMB credentials
        self._register_session()

    def _register_session(self):
        """Register SMB session with credentials."""
        try:
            smbclient.register_session(
                self.server,
                username=self.username,
                password=self.password,
                port=self.port,
                encrypt=False  # Can be configured if needed
            )
        except Exception as e:
            raise StorageConnectionError(f"Failed to register SMB session: {e}")

    def _get_smb_path(self, path: str) -> str:
        """
        Get full SMB UNC path.

        Args:
            path: Relative path within the storage

        Returns:
            Full UNC path (e.g., \\\\server\\share\\path)
        """
        # Clean up the path
        path = path.strip("/")

        # Combine base path and file path
        if self.base_path:
            full_path = f"{self.base_path}/{path}"
        else:
            full_path = path

        # Create UNC path
        unc_path = f"\\\\{self.server}\\{self.share}\\{full_path.replace('/', '\\')}"
        return unc_path

    def _get_parent_path(self, smb_path: str) -> str:
        """Get parent directory of an SMB path."""
        # Remove trailing backslashes
        smb_path = smb_path.rstrip('\\')
        # Find last backslash
        last_slash = smb_path.rfind('\\')
        if last_slash > 0:
            return smb_path[:last_slash]
        return smb_path

    async def upload(
        self,
        source_path: Path,
        destination_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Upload a file to SMB storage."""
        try:
            smb_path = self._get_smb_path(destination_path)

            # Ensure parent directory exists
            parent_dir = self._get_parent_path(smb_path)
            await self._ensure_directory(parent_dir)

            # Calculate checksum while uploading
            md5_hash = hashlib.md5()
            file_size = 0

            def _upload():
                nonlocal file_size
                with open(source_path, 'rb') as src:
                    with open_file(smb_path, mode='wb') as dst:
                        while chunk := src.read(8192):
                            dst.write(chunk)
                            md5_hash.update(chunk)
                            file_size += len(chunk)

            # Run in thread pool to avoid blocking
            await asyncio.get_event_loop().run_in_executor(None, _upload)

            self.logger.info(f"Uploaded {source_path} to SMB: {smb_path}")

            return {
                "path": destination_path,
                "size": file_size,
                "checksum": md5_hash.hexdigest(),
                "backend": "smb"
            }

        except Exception as e:
            self.logger.error(f"Failed to upload to SMB: {e}")
            raise StorageUploadError(f"SMB upload failed: {e}")

    async def upload_stream(
        self,
        stream: BinaryIO,
        destination_path: str,
        size: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Upload a stream to SMB storage."""
        try:
            smb_path = self._get_smb_path(destination_path)

            # Ensure parent directory exists
            parent_dir = self._get_parent_path(smb_path)
            await self._ensure_directory(parent_dir)

            md5_hash = hashlib.md5()
            bytes_written = 0

            def _upload():
                nonlocal bytes_written
                with open_file(smb_path, mode='wb') as dst:
                    while chunk := stream.read(8192):
                        dst.write(chunk)
                        md5_hash.update(chunk)
                        bytes_written += len(chunk)

            await asyncio.get_event_loop().run_in_executor(None, _upload)

            self.logger.info(f"Uploaded stream to SMB: {smb_path}")

            return {
                "path": destination_path,
                "size": bytes_written,
                "checksum": md5_hash.hexdigest(),
                "backend": "smb"
            }

        except Exception as e:
            self.logger.error(f"Failed to upload stream to SMB: {e}")
            raise StorageUploadError(f"SMB stream upload failed: {e}")

    async def download(
        self,
        source_path: str,
        destination_path: Path
    ) -> Dict[str, Any]:
        """Download a file from SMB storage."""
        try:
            smb_path = self._get_smb_path(source_path)

            if not await self.exists(source_path):
                raise StorageNotFoundError(f"File not found: {source_path}")

            # Ensure local parent directory exists
            destination_path.parent.mkdir(parents=True, exist_ok=True)

            md5_hash = hashlib.md5()
            bytes_downloaded = 0

            def _download():
                nonlocal bytes_downloaded
                with open_file(smb_path, mode='rb') as src:
                    with open(destination_path, 'wb') as dst:
                        while chunk := src.read(8192):
                            dst.write(chunk)
                            md5_hash.update(chunk)
                            bytes_downloaded += len(chunk)

            await asyncio.get_event_loop().run_in_executor(None, _download)

            self.logger.info(f"Downloaded from SMB: {smb_path} to {destination_path}")

            return {
                "path": str(destination_path),
                "size": bytes_downloaded,
                "checksum": md5_hash.hexdigest()
            }

        except StorageNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to download from SMB: {e}")
            raise StorageDownloadError(f"SMB download failed: {e}")

    async def download_stream(self, source_path: str) -> BinaryIO:
        """Download a file from SMB storage as a stream."""
        try:
            smb_path = self._get_smb_path(source_path)

            if not await self.exists(source_path):
                raise StorageNotFoundError(f"File not found: {source_path}")

            def _read_to_bytes():
                with open_file(smb_path, mode='rb') as src:
                    return src.read()

            content = await asyncio.get_event_loop().run_in_executor(None, _read_to_bytes)

            self.logger.info(f"Downloaded stream from SMB: {smb_path}")

            return io.BytesIO(content)

        except StorageNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to download stream from SMB: {e}")
            raise StorageDownloadError(f"SMB stream download failed: {e}")

    async def delete(self, path: str) -> bool:
        """Delete a file from SMB storage."""
        try:
            smb_path = self._get_smb_path(path)

            if not await self.exists(path):
                return False

            def _delete():
                remove(smb_path)

            await asyncio.get_event_loop().run_in_executor(None, _delete)

            self.logger.info(f"Deleted from SMB: {smb_path}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete from SMB: {e}")
            return False

    async def list(
        self,
        prefix: str = "",
        recursive: bool = False
    ) -> list[Dict[str, Any]]:
        """List files in SMB storage."""
        try:
            smb_path = self._get_smb_path(prefix)

            files = []

            def _list():
                if not smb_exists(smb_path):
                    return []

                result = []
                for entry in scandir(smb_path):
                    if entry.is_file():
                        file_stat = entry.stat()
                        # Build relative path
                        rel_path = entry.path.replace(f"\\\\{self.server}\\{self.share}\\", "")
                        if self.base_path:
                            rel_path = rel_path.replace(f"{self.base_path}\\", "")
                        rel_path = rel_path.replace("\\", "/")

                        result.append({
                            "path": rel_path,
                            "size": file_stat.st_size,
                            "modified": file_stat.st_mtime,
                            "is_dir": False
                        })
                    elif entry.is_dir() and recursive:
                        # Recursively list subdirectories
                        subdir_path = entry.path.replace(f"\\\\{self.server}\\{self.share}\\", "")
                        if self.base_path:
                            subdir_path = subdir_path.replace(f"{self.base_path}\\", "")
                        subdir_path = subdir_path.replace("\\", "/")
                        # TODO: Implement recursive listing
                        pass

                return result

            files = await asyncio.get_event_loop().run_in_executor(None, _list)

            return files

        except Exception as e:
            self.logger.error(f"Failed to list SMB directory: {e}")
            return []

    async def exists(self, path: str) -> bool:
        """Check if a file exists in SMB storage."""
        try:
            smb_path = self._get_smb_path(path)

            def _exists():
                return smb_exists(smb_path)

            result = await asyncio.get_event_loop().run_in_executor(None, _exists)
            return result

        except Exception as e:
            self.logger.error(f"Failed to check SMB file existence: {e}")
            return False

    async def get_usage(self) -> Dict[str, int]:
        """Get storage usage statistics."""
        try:
            # For SMB, we need to walk the tree and sum up file sizes
            # This can be expensive for large shares
            # For now, return basic info

            smb_path = self._get_smb_path("")

            def _get_size():
                total_size = 0
                try:
                    if smb_exists(smb_path):
                        for entry in scandir(smb_path):
                            if entry.is_file():
                                total_size += entry.stat().st_size
                except Exception:
                    pass
                return total_size

            used = await asyncio.get_event_loop().run_in_executor(None, _get_size)

            # SMB shares typically don't expose capacity info easily
            # This would need to be configured manually or queried via other means
            return {
                "used": used,
                "capacity": 0  # Unknown - should be configured in storage backend settings
            }

        except Exception as e:
            self.logger.error(f"Failed to get SMB usage: {e}")
            return {"used": 0, "capacity": 0}

    async def test_connection(self) -> bool:
        """Test connection to SMB storage."""
        try:
            smb_path = self._get_smb_path("")

            def _test():
                # Try to list the share root
                return smb_exists(smb_path)

            result = await asyncio.get_event_loop().run_in_executor(None, _test)

            if result:
                self.logger.info(f"SMB connection test successful: {self.server}/{self.share}")
            else:
                self.logger.warning(f"SMB path does not exist: {smb_path}")

            return result

        except Exception as e:
            self.logger.error(f"SMB connection test failed: {e}")
            return False

    async def _ensure_directory(self, path: str):
        """Ensure a directory exists, creating it if necessary."""
        try:
            def _mkdir():
                try:
                    # Check if directory already exists
                    if smb_exists(path):
                        return

                    # Try to create the directory (makedirs functionality)
                    mkdir(path)
                except Exception as e:
                    # Directory might already exist or we might not have permission to check
                    # Just log and continue - the file write will fail if directory truly doesn't exist
                    self.logger.debug(f"Directory check/creation for {path}: {e}")
                    pass

            await asyncio.get_event_loop().run_in_executor(None, _mkdir)

        except Exception as e:
            # Don't raise - let the actual file operation fail if needed
            self.logger.warning(f"Could not ensure SMB directory exists: {e}")
