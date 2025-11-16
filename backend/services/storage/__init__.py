"""
Storage backend factory and exports.
"""
from typing import Dict, Any
from backend.models.storage import StorageType
from backend.services.storage.base import StorageBackend, StorageError
from backend.services.storage.local import LocalStorage
from backend.services.storage.s3 import S3Storage
from backend.services.storage.smb import SMBStorage


def create_storage_backend(
    storage_type: StorageType,
    config: Dict[str, Any]
) -> StorageBackend:
    """
    Factory function to create storage backend instances.

    Args:
        storage_type: Type of storage backend
        config: Configuration dictionary for the backend

    Returns:
        Initialized storage backend instance

    Raises:
        StorageError: If storage type is not supported
    """
    if storage_type == StorageType.LOCAL:
        return LocalStorage(config)
    elif storage_type == StorageType.S3:
        return S3Storage(config)
    elif storage_type == StorageType.SMB:
        return SMBStorage(config)
    elif storage_type == StorageType.NFS:
        # TODO: Implement NFS storage
        raise StorageError("NFS storage not yet implemented")
    else:
        raise StorageError(f"Unsupported storage type: {storage_type}")


__all__ = [
    "StorageBackend",
    "StorageError",
    "LocalStorage",
    "S3Storage",
    "SMBStorage",
    "create_storage_backend"
]
