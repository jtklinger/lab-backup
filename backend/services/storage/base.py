"""
Base storage backend interface.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, BinaryIO
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize storage backend.

        Args:
            config: Storage-specific configuration dictionary
        """
        self.config = config
        self.logger = logger

    @abstractmethod
    async def upload(
        self,
        source_path: Path,
        destination_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Upload a file to storage.

        Args:
            source_path: Local file path to upload
            destination_path: Destination path in storage
            metadata: Optional metadata to attach to the file

        Returns:
            Dictionary with upload information (size, checksum, etc.)
        """
        pass

    @abstractmethod
    async def upload_stream(
        self,
        stream: BinaryIO,
        destination_path: str,
        size: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Upload a file stream to storage.

        Args:
            stream: File-like object to upload
            destination_path: Destination path in storage
            size: Size of the stream in bytes
            metadata: Optional metadata to attach to the file

        Returns:
            Dictionary with upload information
        """
        pass

    @abstractmethod
    async def download(
        self,
        source_path: str,
        destination_path: Path
    ) -> Dict[str, Any]:
        """
        Download a file from storage.

        Args:
            source_path: Source path in storage
            destination_path: Local file path to save to

        Returns:
            Dictionary with download information
        """
        pass

    @abstractmethod
    async def download_stream(
        self,
        source_path: str
    ) -> BinaryIO:
        """
        Download a file from storage as a stream.

        Args:
            source_path: Source path in storage

        Returns:
            File-like object
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        Delete a file from storage.

        Args:
            path: Path to file in storage

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def list(
        self,
        prefix: str = "",
        recursive: bool = False
    ) -> list[Dict[str, Any]]:
        """
        List files in storage.

        Args:
            prefix: Path prefix to filter by
            recursive: Whether to list recursively

        Returns:
            List of file information dictionaries
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            path: Path to file in storage

        Returns:
            True if file exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_usage(self) -> Dict[str, int]:
        """
        Get storage usage statistics.

        Returns:
            Dictionary with 'used' and 'capacity' in bytes
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test connection to storage backend.

        Returns:
            True if connection is successful, False otherwise
        """
        pass


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class StorageConnectionError(StorageError):
    """Exception raised when connection to storage fails."""
    pass


class StorageUploadError(StorageError):
    """Exception raised when upload fails."""
    pass


class StorageDownloadError(StorageError):
    """Exception raised when download fails."""
    pass


class StorageNotFoundError(StorageError):
    """Exception raised when file is not found."""
    pass
