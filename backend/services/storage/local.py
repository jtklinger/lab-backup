"""
Local filesystem storage backend.
"""
import os
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, BinaryIO
import aiofiles
import aiofiles.os

from backend.services.storage.base import (
    StorageBackend,
    StorageError,
    StorageUploadError,
    StorageDownloadError,
    StorageNotFoundError
)


class LocalStorage(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize local storage.

        Config format:
        {
            "base_path": "/path/to/backups"
        }
        """
        super().__init__(config)
        self.base_path = Path(config["base_path"])

        # Create base directory if it doesn't exist
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path: str) -> Path:
        """Get full filesystem path from relative path."""
        full_path = self.base_path / path
        # Ensure path is within base_path (security check)
        if not str(full_path.resolve()).startswith(str(self.base_path.resolve())):
            raise StorageError(f"Path {path} is outside base path")
        return full_path

    async def upload(
        self,
        source_path: Path,
        destination_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Upload a file to local storage."""
        try:
            dest_path = self._get_full_path(destination_path)
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Calculate checksum while copying
            hasher = hashlib.sha256()
            size = 0

            async with aiofiles.open(source_path, 'rb') as src:
                async with aiofiles.open(dest_path, 'wb') as dst:
                    while chunk := await src.read(8192):
                        await dst.write(chunk)
                        hasher.update(chunk)
                        size += len(chunk)

            return {
                "path": destination_path,
                "size": size,
                "checksum": hasher.hexdigest()
            }

        except Exception as e:
            self.logger.error(f"Failed to upload file to local storage: {e}")
            raise StorageUploadError(f"Upload failed: {e}")

    async def upload_stream(
        self,
        stream: BinaryIO,
        destination_path: str,
        size: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Upload a file stream to local storage."""
        try:
            dest_path = self._get_full_path(destination_path)
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            hasher = hashlib.sha256()
            written = 0

            async with aiofiles.open(dest_path, 'wb') as dst:
                while chunk := stream.read(8192):
                    await dst.write(chunk)
                    hasher.update(chunk)
                    written += len(chunk)

            return {
                "path": destination_path,
                "size": written,
                "checksum": hasher.hexdigest()
            }

        except Exception as e:
            self.logger.error(f"Failed to upload stream to local storage: {e}")
            raise StorageUploadError(f"Upload failed: {e}")

    async def download(
        self,
        source_path: str,
        destination_path: Path
    ) -> Dict[str, Any]:
        """Download a file from local storage."""
        try:
            src_path = self._get_full_path(source_path)

            if not await aiofiles.os.path.exists(src_path):
                raise StorageNotFoundError(f"File not found: {source_path}")

            destination_path.parent.mkdir(parents=True, exist_ok=True)

            hasher = hashlib.sha256()
            size = 0

            async with aiofiles.open(src_path, 'rb') as src:
                async with aiofiles.open(destination_path, 'wb') as dst:
                    while chunk := await src.read(8192):
                        await dst.write(chunk)
                        hasher.update(chunk)
                        size += len(chunk)

            return {
                "path": str(destination_path),
                "size": size,
                "checksum": hasher.hexdigest()
            }

        except StorageNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to download file from local storage: {e}")
            raise StorageDownloadError(f"Download failed: {e}")

    async def download_stream(self, source_path: str) -> BinaryIO:
        """Download a file from local storage as a stream."""
        try:
            src_path = self._get_full_path(source_path)

            if not await aiofiles.os.path.exists(src_path):
                raise StorageNotFoundError(f"File not found: {source_path}")

            return await aiofiles.open(src_path, 'rb')

        except StorageNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to open file stream from local storage: {e}")
            raise StorageDownloadError(f"Download failed: {e}")

    async def delete(self, path: str) -> bool:
        """Delete a file from local storage."""
        try:
            file_path = self._get_full_path(path)

            if not await aiofiles.os.path.exists(file_path):
                return False

            await aiofiles.os.remove(file_path)

            # Try to remove empty parent directories
            try:
                parent = file_path.parent
                while parent != self.base_path:
                    if not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent
                    else:
                        break
            except Exception:
                pass  # Ignore errors in cleanup

            return True

        except Exception as e:
            self.logger.error(f"Failed to delete file from local storage: {e}")
            return False

    async def list(
        self,
        prefix: str = "",
        recursive: bool = False
    ) -> list[Dict[str, Any]]:
        """List files in local storage."""
        try:
            search_path = self._get_full_path(prefix) if prefix else self.base_path

            if not await aiofiles.os.path.exists(search_path):
                return []

            files = []
            if recursive:
                for root, _, filenames in os.walk(search_path):
                    for filename in filenames:
                        file_path = Path(root) / filename
                        rel_path = file_path.relative_to(self.base_path)
                        stat = await aiofiles.os.stat(file_path)
                        files.append({
                            "path": str(rel_path),
                            "size": stat.st_size,
                            "modified": stat.st_mtime
                        })
            else:
                if search_path.is_file():
                    stat = await aiofiles.os.stat(search_path)
                    files.append({
                        "path": prefix,
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })
                elif search_path.is_dir():
                    for item in search_path.iterdir():
                        if item.is_file():
                            rel_path = item.relative_to(self.base_path)
                            stat = await aiofiles.os.stat(item)
                            files.append({
                                "path": str(rel_path),
                                "size": stat.st_size,
                                "modified": stat.st_mtime
                            })

            return files

        except Exception as e:
            self.logger.error(f"Failed to list files in local storage: {e}")
            return []

    async def exists(self, path: str) -> bool:
        """Check if a file exists in local storage."""
        try:
            file_path = self._get_full_path(path)
            return await aiofiles.os.path.exists(file_path)
        except Exception:
            return False

    async def get_usage(self) -> Dict[str, int]:
        """Get storage usage statistics."""
        try:
            stat = os.statvfs(self.base_path)
            capacity = stat.f_blocks * stat.f_frsize
            used = (stat.f_blocks - stat.f_bfree) * stat.f_frsize

            return {
                "used": used,
                "capacity": capacity,
                "available": stat.f_bavail * stat.f_frsize
            }

        except Exception as e:
            self.logger.error(f"Failed to get storage usage: {e}")
            return {"used": 0, "capacity": 0, "available": 0}

    async def test_connection(self) -> bool:
        """Test connection to local storage."""
        try:
            # Check if base path is accessible and writable
            test_file = self.base_path / ".test_write"
            async with aiofiles.open(test_file, 'w') as f:
                await f.write("test")
            await aiofiles.os.remove(test_file)
            return True
        except Exception as e:
            self.logger.error(f"Local storage connection test failed: {e}")
            return False
