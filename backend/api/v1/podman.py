"""
Podman API endpoints.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.models.infrastructure import PodmanHost, Container
from backend.core.security import get_current_user

router = APIRouter()


class PodmanHostResponse(BaseModel):
    id: int
    name: str
    uri: str
    enabled: bool

    class Config:
        from_attributes = True


class ContainerResponse(BaseModel):
    id: int
    name: str
    container_id: str
    image: Optional[str]
    state: str

    class Config:
        from_attributes = True


@router.get("/hosts", response_model=List[PodmanHostResponse])
async def list_hosts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all Podman hosts."""
    stmt = select(PodmanHost)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/containers", response_model=List[ContainerResponse])
async def list_all_containers(
    host_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all containers across all Podman hosts, optionally filtered by host_id."""
    if host_id:
        stmt = select(Container).where(Container.podman_host_id == host_id)
    else:
        stmt = select(Container)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/hosts/{host_id}/containers", response_model=List[ContainerResponse])
async def list_containers(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List containers on a Podman host."""
    stmt = select(Container).where(Container.podman_host_id == host_id)
    result = await db.execute(stmt)
    return result.scalars().all()
