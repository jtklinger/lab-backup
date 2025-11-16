"""
Podman API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.infrastructure import PodmanHost, Container
from backend.core.security import get_current_user, require_role
from backend.services.podman.backup import PodmanBackupService

router = APIRouter()


class PodmanHostCreate(BaseModel):
    """Podman host creation model."""
    name: str
    uri: str
    config: Optional[dict] = None


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


@router.post("/hosts", response_model=PodmanHostResponse, status_code=status.HTTP_201_CREATED)
async def create_host(
    host_data: PodmanHostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Create a new Podman host."""
    # TODO: Test connection to Podman host before adding

    host = PodmanHost(
        name=host_data.name,
        uri=host_data.uri,
        config=host_data.config or {},
        enabled=True
    )

    db.add(host)
    await db.commit()
    await db.refresh(host)

    return host


@router.post("/hosts/{host_id}/refresh")
async def refresh_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Refresh containers from Podman host."""
    # Get host
    host = await db.get(PodmanHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Podman host not found"
        )

    # Sync containers from Podman
    podman_service = PodmanBackupService()
    try:
        containers_data = await podman_service.list_containers(host.uri)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect to Podman host: {str(e)}"
        )

    # Update database
    synced_count = 0
    for container_data in containers_data:
        stmt = select(Container).where(Container.container_id == container_data["id"])
        result = await db.execute(stmt)
        container = result.scalar_one_or_none()

        if container:
            # Update existing
            container.name = container_data["name"]
            container.image = container_data["image"]
            container.state = container_data["state"]
        else:
            # Create new
            container = Container(
                podman_host_id=host.id,
                name=container_data["name"],
                container_id=container_data["id"],
                image=container_data["image"],
                state=container_data["state"]
            )
            db.add(container)
        synced_count += 1

    await db.commit()

    return {
        "message": f"Successfully synced {synced_count} containers from {host.name}",
        "count": synced_count
    }


@router.delete("/hosts/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Delete a Podman host."""
    host = await db.get(PodmanHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Podman host not found"
        )

    await db.delete(host)
    await db.commit()
    return None


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
