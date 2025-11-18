"""
Compliance tracking API endpoints.

Provides endpoints for monitoring backup compliance status,
viewing compliance dashboard, and triggering compliance calculations.

Related: Issue #8 - Build Compliance Tracking System
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.infrastructure import VM, Container
from backend.models.backup import SourceType
from backend.core.security import get_current_user, require_role
from backend.services.compliance import ComplianceService
from backend.worker import calculate_compliance

router = APIRouter()


class ComplianceStatusResponse(BaseModel):
    """Compliance status for a single VM or Container."""
    id: int
    name: str
    source_type: str  # "vm" or "container"
    compliance_status: Optional[str] = None
    compliance_reason: Optional[str] = None
    last_successful_backup: Optional[datetime] = None
    compliance_last_checked: Optional[datetime] = None

    class Config:
        from_attributes = True


class ComplianceDashboardResponse(BaseModel):
    """Compliance dashboard overview."""
    vms: Dict[str, int] = Field(..., description="VM compliance breakdown (total, grey, green, yellow, red)")
    containers: Dict[str, int] = Field(..., description="Container compliance breakdown")
    last_updated: Optional[str] = Field(None, description="ISO timestamp of last compliance check")


class NonCompliantEntityResponse(BaseModel):
    """Non-compliant entity details."""
    id: int
    name: str
    reason: Optional[str] = None
    last_backup: Optional[str] = None
    last_checked: Optional[str] = None


class NonCompliantResponse(BaseModel):
    """Non-compliant VMs and containers."""
    vms: List[NonCompliantEntityResponse]
    containers: List[NonCompliantEntityResponse]


class ComplianceCalculationResponse(BaseModel):
    """Response from triggering compliance calculation."""
    task_id: str
    message: str


@router.get("/dashboard", response_model=ComplianceDashboardResponse)
async def get_compliance_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get compliance overview dashboard.

    Returns compliance statistics for all VMs and containers:
    - Total count
    - Breakdown by status (GREY, GREEN, YELLOW, RED)
    - Last update timestamp

    **Permissions**: All authenticated users
    """
    compliance_service = ComplianceService(db)
    dashboard = await compliance_service.get_compliance_dashboard()
    return dashboard


@router.get("/non-compliant", response_model=NonCompliantResponse)
async def get_non_compliant(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all non-compliant (RED status) VMs and containers.

    Useful for alerting and reporting purposes.

    **Permissions**: All authenticated users
    """
    compliance_service = ComplianceService(db)
    non_compliant = await compliance_service.get_non_compliant_entities()
    return non_compliant


@router.get("/vms", response_model=List[ComplianceStatusResponse])
async def get_vm_compliance(
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get compliance status for all VMs.

    **Query Parameters**:
    - `status_filter` (optional): Filter by status (GREY, GREEN, YELLOW, RED)

    **Permissions**: All authenticated users
    """
    stmt = select(VM)

    if status_filter:
        status_upper = status_filter.upper()
        if status_upper not in ["GREY", "GREEN", "YELLOW", "RED"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}. Must be GREY, GREEN, YELLOW, or RED."
            )
        stmt = stmt.where(VM.compliance_status == status_upper)

    result = await db.execute(stmt)
    vms = result.scalars().all()

    return [
        ComplianceStatusResponse(
            id=vm.id,
            name=vm.name,
            source_type="vm",
            compliance_status=vm.compliance_status,
            compliance_reason=vm.compliance_reason,
            last_successful_backup=vm.last_successful_backup,
            compliance_last_checked=vm.compliance_last_checked
        )
        for vm in vms
    ]


@router.get("/containers", response_model=List[ComplianceStatusResponse])
async def get_container_compliance(
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get compliance status for all containers.

    **Query Parameters**:
    - `status_filter` (optional): Filter by status (GREY, GREEN, YELLOW, RED)

    **Permissions**: All authenticated users
    """
    stmt = select(Container)

    if status_filter:
        status_upper = status_filter.upper()
        if status_upper not in ["GREY", "GREEN", "YELLOW", "RED"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}. Must be GREY, GREEN, YELLOW, or RED."
            )
        stmt = stmt.where(Container.compliance_status == status_upper)

    result = await db.execute(stmt)
    containers = result.scalars().all()

    return [
        ComplianceStatusResponse(
            id=container.id,
            name=container.name,
            source_type="container",
            compliance_status=container.compliance_status,
            compliance_reason=container.compliance_reason,
            last_successful_backup=container.last_successful_backup,
            compliance_last_checked=container.compliance_last_checked
        )
        for container in containers
    ]


@router.get("/vms/{vm_id}", response_model=ComplianceStatusResponse)
async def get_vm_compliance_by_id(
    vm_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get compliance status for a specific VM.

    **Permissions**: All authenticated users
    """
    vm = await db.get(VM, vm_id)
    if not vm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"VM with ID {vm_id} not found"
        )

    return ComplianceStatusResponse(
        id=vm.id,
        name=vm.name,
        source_type="vm",
        compliance_status=vm.compliance_status,
        compliance_reason=vm.compliance_reason,
        last_successful_backup=vm.last_successful_backup,
        compliance_last_checked=vm.compliance_last_checked
    )


@router.get("/containers/{container_id}", response_model=ComplianceStatusResponse)
async def get_container_compliance_by_id(
    container_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get compliance status for a specific container.

    **Permissions**: All authenticated users
    """
    container = await db.get(Container, container_id)
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Container with ID {container_id} not found"
        )

    return ComplianceStatusResponse(
        id=container.id,
        name=container.name,
        source_type="container",
        compliance_status=container.compliance_status,
        compliance_reason=container.compliance_reason,
        last_successful_backup=container.last_successful_backup,
        compliance_last_checked=container.compliance_last_checked
    )


@router.post("/calculate", response_model=ComplianceCalculationResponse)
async def trigger_compliance_calculation(
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """
    Manually trigger compliance calculation for all VMs and containers.

    This endpoint queues a Celery task to recalculate compliance status
    for all entities. Normally runs automatically every hour.

    **Permissions**: Admin only
    """
    task = calculate_compliance.delay()

    return ComplianceCalculationResponse(
        task_id=task.id,
        message="Compliance calculation task queued successfully"
    )


@router.post("/vms/{vm_id}/calculate", response_model=ComplianceStatusResponse)
async def calculate_vm_compliance(
    vm_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """
    Calculate and update compliance status for a specific VM.

    **Permissions**: Admin only
    """
    vm = await db.get(VM, vm_id)
    if not vm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"VM with ID {vm_id} not found"
        )

    compliance_service = ComplianceService(db)
    success = await compliance_service.update_vm_compliance(vm_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update VM compliance"
        )

    # Refresh VM to get updated values
    await db.refresh(vm)

    return ComplianceStatusResponse(
        id=vm.id,
        name=vm.name,
        source_type="vm",
        compliance_status=vm.compliance_status,
        compliance_reason=vm.compliance_reason,
        last_successful_backup=vm.last_successful_backup,
        compliance_last_checked=vm.compliance_last_checked
    )


@router.post("/containers/{container_id}/calculate", response_model=ComplianceStatusResponse)
async def calculate_container_compliance(
    container_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """
    Calculate and update compliance status for a specific container.

    **Permissions**: Admin only
    """
    container = await db.get(Container, container_id)
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Container with ID {container_id} not found"
        )

    compliance_service = ComplianceService(db)
    success = await compliance_service.update_container_compliance(container_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update container compliance"
        )

    # Refresh container to get updated values
    await db.refresh(container)

    return ComplianceStatusResponse(
        id=container.id,
        name=container.name,
        source_type="container",
        compliance_status=container.compliance_status,
        compliance_reason=container.compliance_reason,
        last_successful_backup=container.last_successful_backup,
        compliance_last_checked=container.compliance_last_checked
    )
