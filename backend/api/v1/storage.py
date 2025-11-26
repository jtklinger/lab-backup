"""
Storage backend API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.storage import StorageBackend, StorageType
from backend.core.security import get_current_user, require_role
from backend.services.storage import create_storage_backend as create_storage

router = APIRouter()


class StorageBackendCreate(BaseModel):
    name: str
    type: StorageType
    config: dict
    threshold: int = 80
    quota_gb: Optional[int] = None  # Manual quota in GB


class StorageBackendUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None
    threshold: Optional[int] = None
    quota_gb: Optional[int] = None


class StorageBackendResponse(BaseModel):
    id: int
    name: str
    type: StorageType
    config: dict
    enabled: bool
    capacity: Optional[int]
    used: Optional[int]
    quota_gb: Optional[int]
    threshold: int
    last_check: Optional[str]
    encryption_strategy: Optional[str]
    encryption_key_id: Optional[int]
    encryption_config: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[StorageBackendResponse])
async def list_storage_backends(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all storage backends."""
    stmt = select(StorageBackend)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=StorageBackendResponse, status_code=status.HTTP_201_CREATED)
async def create_storage_backend(
    backend_data: StorageBackendCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Create a new storage backend."""
    # Test connection
    try:
        storage = create_storage(backend_data.type, backend_data.config)
        if not await storage.test_connection():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to connect to storage backend"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Storage configuration error: {str(e)}"
        )

    backend = StorageBackend(
        name=backend_data.name,
        type=backend_data.type,
        config=backend_data.config,
        threshold=backend_data.threshold,
        quota_gb=backend_data.quota_gb,
        enabled=True
    )

    db.add(backend)
    await db.commit()
    await db.refresh(backend)

    return backend


@router.put("/{backend_id}", response_model=StorageBackendResponse)
async def update_storage_backend(
    backend_id: int,
    update_data: StorageBackendUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Update a storage backend."""
    backend = await db.get(StorageBackend, backend_id)
    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage backend not found"
        )

    # Update only provided fields
    if update_data.name is not None:
        backend.name = update_data.name
    if update_data.enabled is not None:
        backend.enabled = update_data.enabled
    if update_data.threshold is not None:
        backend.threshold = update_data.threshold
    if update_data.quota_gb is not None:
        backend.quota_gb = update_data.quota_gb
    if update_data.config is not None:
        # Test new config before applying
        try:
            storage = create_storage(backend.type, update_data.config)
            if not await storage.test_connection():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to connect with new configuration"
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid configuration: {str(e)}"
            )
        backend.config = update_data.config

    await db.commit()
    await db.refresh(backend)
    return backend


@router.delete("/{backend_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_storage_backend(
    backend_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """Delete a storage backend (Admin only)."""
    backend = await db.get(StorageBackend, backend_id)
    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage backend not found"
        )

    # Check if backend has any backups
    from backend.models.backup import Backup
    stmt = select(Backup).where(Backup.storage_backend_id == backend_id).limit(1)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete storage backend with existing backups"
        )

    await db.delete(backend)
    await db.commit()


@router.get("/{backend_id}")
async def get_storage_backend(
    backend_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific storage backend."""
    stmt = select(StorageBackend).where(StorageBackend.id == backend_id)
    result = await db.execute(stmt)
    backend = result.scalar_one_or_none()

    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage backend not found"
        )

    return {
        "id": backend.id,
        "name": backend.name,
        "type": backend.type,
        "enabled": backend.enabled,
        "capacity": backend.capacity,
        "used": backend.used,
        "threshold": backend.threshold
    }


@router.post("/{backend_id}/test")
async def test_storage_backend(
    backend_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Test connection to a storage backend."""
    stmt = select(StorageBackend).where(StorageBackend.id == backend_id)
    result = await db.execute(stmt)
    backend = result.scalar_one_or_none()

    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage backend not found"
        )

    try:
        storage = create_storage(backend.type, backend.config)
        success = await storage.test_connection()

        if success:
            return {
                "success": True,
                "message": "Successfully connected to storage backend"
            }
        else:
            return {
                "success": False,
                "message": "Failed to connect to storage backend"
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection test failed: {str(e)}"
        }


@router.get("/{backend_id}/usage")
async def get_storage_usage(
    backend_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get storage usage statistics."""
    backend = await db.get(StorageBackend, backend_id)
    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage backend not found"
        )

    storage = create_storage(backend.type, backend.config)
    usage = await storage.get_usage()

    # Determine capacity: use auto-detected if available, otherwise use quota_gb
    used_bytes = usage.get("used", 0)
    auto_capacity = usage.get("capacity", 0)

    if auto_capacity > 0:
        capacity_bytes = auto_capacity
    elif backend.quota_gb:
        capacity_bytes = backend.quota_gb * (1024 ** 3)
    else:
        capacity_bytes = 0

    # Calculate percentages
    used_percent = (used_bytes / capacity_bytes) * 100 if capacity_bytes > 0 else 0
    threshold_exceeded = used_percent >= backend.threshold if capacity_bytes > 0 else False

    return {
        "backend_id": backend_id,
        "name": backend.name,
        "used": used_bytes,
        "used_gb": round(used_bytes / (1024 ** 3), 2),
        "capacity": capacity_bytes,
        "capacity_gb": round(capacity_bytes / (1024 ** 3), 2) if capacity_bytes > 0 else None,
        "quota_gb": backend.quota_gb,
        "available": capacity_bytes - used_bytes if capacity_bytes > 0 else 0,
        "used_percent": round(used_percent, 1),
        "threshold": backend.threshold,
        "threshold_exceeded": threshold_exceeded
    }
