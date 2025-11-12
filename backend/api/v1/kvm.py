"""
KVM/libvirt API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.infrastructure import KVMHost, VM
from backend.core.security import get_current_user, require_role
from backend.services.kvm.backup import KVMBackupService

router = APIRouter()


class KVMHostCreate(BaseModel):
    """KVM host creation model."""
    name: str
    uri: str
    username: Optional[str] = None
    auth_type: str = "ssh"
    config: Optional[dict] = None


class KVMHostResponse(BaseModel):
    """KVM host response model."""
    id: int
    name: str
    uri: str
    enabled: bool
    last_sync: Optional[str]

    class Config:
        from_attributes = True


class VMResponse(BaseModel):
    """VM response model."""
    id: int
    kvm_host_id: int
    name: str
    uuid: str
    vcpus: Optional[int]
    memory: Optional[int]
    disk_size: Optional[int]
    state: str

    class Config:
        from_attributes = True


@router.get("/hosts", response_model=List[KVMHostResponse])
async def list_hosts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all KVM hosts."""
    stmt = select(KVMHost)
    result = await db.execute(stmt)
    hosts = result.scalars().all()
    return hosts


@router.post("/hosts", response_model=KVMHostResponse, status_code=status.HTTP_201_CREATED)
async def create_host(
    host_data: KVMHostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """Create a new KVM host."""
    # Test connection first
    kvm_service = KVMBackupService()
    if not await kvm_service.test_connection(host_data.uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to connect to KVM host"
        )

    host = KVMHost(
        name=host_data.name,
        uri=host_data.uri,
        username=host_data.username,
        auth_type=host_data.auth_type,
        config=host_data.config or {},
        enabled=True
    )

    db.add(host)
    await db.commit()
    await db.refresh(host)

    return host


@router.get("/hosts/{host_id}/vms", response_model=List[VMResponse])
async def list_vms(
    host_id: int,
    sync: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List VMs on a KVM host."""
    # Get host
    host = await db.get(KVMHost, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KVM host not found"
        )

    if sync:
        # Sync VMs from libvirt
        kvm_service = KVMBackupService()
        vms_data = await kvm_service.list_vms(host.uri)

        # Update database
        for vm_data in vms_data:
            stmt = select(VM).where(VM.uuid == vm_data["uuid"])
            result = await db.execute(stmt)
            vm = result.scalar_one_or_none()

            if vm:
                # Update existing
                vm.name = vm_data["name"]
                vm.state = vm_data["state"]
                vm.vcpus = vm_data["vcpus"]
                vm.memory = vm_data["memory"]
            else:
                # Create new
                vm = VM(
                    kvm_host_id=host.id,
                    name=vm_data["name"],
                    uuid=vm_data["uuid"],
                    vcpus=vm_data["vcpus"],
                    memory=vm_data["memory"],
                    state=vm_data["state"]
                )
                db.add(vm)

        await db.commit()

    # Return VMs from database
    stmt = select(VM).where(VM.kvm_host_id == host_id)
    result = await db.execute(stmt)
    vms = result.scalars().all()

    return vms


@router.get("/vms/{vm_id}", response_model=VMResponse)
async def get_vm(
    vm_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get VM details."""
    vm = await db.get(VM, vm_id)
    if not vm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VM not found"
        )
    return vm
