"""
Storage backend API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

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


class StorageBackendResponse(BaseModel):
    id: int
    name: str
    type: StorageType
    enabled: bool
    capacity: Optional[int]
    used: Optional[int]
    threshold: int

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
        enabled=True
    )

    db.add(backend)
    await db.commit()
    await db.refresh(backend)

    return backend


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

    return {
        "backend_id": backend_id,
        "name": backend.name,
        "used": usage.get("used", 0),
        "capacity": usage.get("capacity", 0),
        "available": usage.get("available", 0),
        "used_percent": (usage.get("used", 0) / usage.get("capacity", 1)) * 100 if usage.get("capacity", 0) > 0 else 0
    }
