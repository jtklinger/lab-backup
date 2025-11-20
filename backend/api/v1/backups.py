"""
Backup API endpoints.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import List, Optional, Generic, TypeVar

from backend.models.base import get_db
from backend.models.user import User, UserRole
from backend.models.backup import Backup, BackupStatus, BackupMode, ScheduleType, SourceType
from backend.models.infrastructure import VM, Container
from backend.models.settings import SystemSetting
from backend.core.security import get_current_user, require_role

router = APIRouter()

# Generic paginated response
T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response model."""
    items: List[T]
    total: int
    limit: int
    offset: int


class BackupResponse(BaseModel):
    id: int
    schedule_id: Optional[int]
    source_name: str
    source_type: SourceType
    backup_type: ScheduleType
    backup_mode: BackupMode
    parent_backup_id: Optional[int]
    status: BackupStatus
    size: Optional[int]
    compressed_size: Optional[int]
    storage_path: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    expires_at: Optional[datetime]
    # Verification fields (Issue #6)
    verified: bool = False
    verification_date: Optional[datetime] = None
    verification_status: Optional[str] = None
    verification_error: Optional[str] = None
    verified_table_count: Optional[int] = None
    verified_size_bytes: Optional[int] = None
    verification_duration_seconds: Optional[int] = None
    # Chain tracking fields (Issue #10)
    chain_id: Optional[str] = None
    sequence_number: Optional[int] = None
    original_size: Optional[int] = None
    dedupe_ratio: Optional[float] = None
    compression_ratio: Optional[float] = None
    space_saved_bytes: Optional[int] = None
    # Immutability fields (Issue #13)
    immutable: bool = False
    retention_until: Optional[datetime] = None
    retention_mode: Optional[str] = None
    immutability_reason: Optional[str] = None
    # Storage encryption metadata (Issue #12)
    storage_encryption_type: Optional[str] = "NONE"
    storage_encryption_key_id: Optional[str] = None

    class Config:
        from_attributes = True


class TriggerBackupRequest(BaseModel):
    """Request model for triggering one-time backup."""
    source_type: SourceType = Field(..., description="Type of source: vm or container")
    source_id: int = Field(..., description="ID of the VM or Container to backup")
    backup_mode: BackupMode = Field(BackupMode.FULL, description="Backup mode: full or incremental")
    storage_backend_id: int = Field(..., description="ID of storage backend to use")
    encryption_enabled: bool = Field(False, description="Whether to encrypt the backup")
    retention_days: Optional[int] = Field(None, description="Retention period in days (defaults to system setting)")


async def find_parent_backup(
    source_type: SourceType,
    source_id: int,
    db: AsyncSession
) -> Optional[Backup]:
    """Find the most recent completed FULL backup for the given source."""
    stmt = select(Backup).where(
        and_(
            Backup.source_type == source_type,
            Backup.source_id == source_id,
            Backup.backup_mode == BackupMode.FULL,
            Backup.status == BackupStatus.COMPLETED
        )
    ).order_by(Backup.completed_at.desc()).limit(1)

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post("/trigger", response_model=BackupResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_backup(
    request: TriggerBackupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """
    Trigger a one-time backup of a VM or container.

    For INCREMENTAL backups, the system automatically finds the most recent FULL backup
    as the parent. If no parent backup exists, returns an error.
    """
    # Validate source exists
    if request.source_type == SourceType.VM:
        source = await db.get(VM, request.source_id)
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"VM with ID {request.source_id} not found"
            )
        source_name = source.name
    elif request.source_type == SourceType.CONTAINER:
        source = await db.get(Container, request.source_id)
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Container with ID {request.source_id} not found"
            )
        source_name = source.name
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source_type: {request.source_type}"
        )

    # For incremental backups, find parent backup
    parent_backup_id = None
    if request.backup_mode == BackupMode.INCREMENTAL:
        parent_backup = await find_parent_backup(request.source_type, request.source_id, db)
        if not parent_backup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No parent FULL backup found for {request.source_type} {source_name}. "
                       "Create a FULL backup first before running incremental backups."
            )
        parent_backup_id = parent_backup.id

    # Get retention period
    retention_days = request.retention_days
    if retention_days is None:
        # Load from system settings
        stmt = select(SystemSetting).where(SystemSetting.key == "default_one_time_retention_days")
        result = await db.execute(stmt)
        setting = result.scalar_one_or_none()
        retention_days = int(setting.value) if setting else 30

    # Calculate expiration date
    expires_at = datetime.utcnow() + timedelta(days=retention_days)

    # Create backup record
    backup = Backup(
        schedule_id=None,  # One-time backup has no schedule
        source_type=request.source_type,
        source_id=request.source_id,
        source_name=source_name,
        backup_type=ScheduleType.DAILY,  # One-time backups use "daily" type
        backup_mode=request.backup_mode,
        parent_backup_id=parent_backup_id,
        status=BackupStatus.PENDING,
        storage_backend_id=request.storage_backend_id,
        expires_at=expires_at,
        backup_metadata={
            "one_time": True,
            "encryption_enabled": request.encryption_enabled,
            "triggered_by": current_user.username,
            "triggered_at": datetime.utcnow().isoformat()
        }
    )

    db.add(backup)
    await db.commit()
    await db.refresh(backup)

    # Queue backup job via Celery
    from backend.worker import execute_backup
    task = execute_backup.delay(None, backup.id)  # schedule_id is None for one-time backups

    # Update backup with task ID
    from backend.models.backup import Job, JobType, JobStatus
    job = Job(
        type=JobType.BACKUP,
        status=JobStatus.PENDING,
        backup_id=backup.id,
        celery_task_id=task.id
    )
    db.add(job)
    await db.commit()
    await db.refresh(backup)

    return backup


@router.get("", response_model=PaginatedResponse[BackupResponse])
async def list_backups(
    status: Optional[BackupStatus] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List backups with optional filtering."""
    # Build base query
    stmt = select(Backup)
    if status:
        stmt = stmt.where(Backup.status == status)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Get paginated items
    stmt = stmt.order_by(Backup.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{backup_id}", response_model=BackupResponse)
async def get_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get backup details."""
    backup = await db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )
    return backup


@router.delete("/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    backup_id: int,
    override_governance: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """
    Delete a backup.

    Args:
        backup_id: ID of backup to delete
        override_governance: If True, bypass GOVERNANCE mode retention (admin only)

    Raises:
        403: If backup is immutable and cannot be deleted
        404: If backup not found

    Related: Issue #13 - Immutable Backup Support
    """
    backup = await db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )

    # Check immutability protection (Issue #13)
    from backend.services.immutability import ImmutabilityService
    immutability_service = ImmutabilityService(db)

    is_admin = current_user.role == UserRole.ADMIN
    can_delete, reason = await immutability_service.can_delete_backup(
        backup_id,
        is_admin=is_admin,
        override_governance=override_governance
    )

    if not can_delete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete backup: {reason}"
        )

    # Check backup chain dependencies (Issue #10)
    from backend.services.backup_chain import BackupChainService
    chain_service = BackupChainService(db)
    can_delete_chain, chain_reason = await chain_service.can_delete_backup(backup_id)

    if not can_delete_chain:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete backup: {chain_reason}. Delete dependent backups first."
        )

    # Delete from storage
    if backup.storage_path:
        from backend.services.storage import create_storage_backend
        from backend.models.storage import StorageBackend as StorageBackendModel

        storage_backend = await db.get(StorageBackendModel, backup.storage_backend_id)
        if storage_backend:
            storage = create_storage_backend(storage_backend.type, storage_backend.config)

            # For S3 with Object Lock, pass override flag
            if storage_backend.type == "s3":
                await storage.delete(backup.storage_path, bypass_governance=override_governance and is_admin)
            else:
                await storage.delete(backup.storage_path)

    # Delete from database (may be blocked by PostgreSQL trigger)
    try:
        await db.delete(backup)
        await db.commit()
    except Exception as e:
        await db.rollback()
        # Database trigger blocked deletion
        if "immutable" in str(e).lower() or "COMPLIANCE" in str(e) or "LEGAL_HOLD" in str(e):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Database protection: {str(e)}"
            )
        raise

    return None


class RestoreBackupRequest(BaseModel):
    """Request model for restoring a backup."""
    target_host_id: Optional[int] = Field(None, description="ID of target host (None = original host)")
    new_name: Optional[str] = Field(None, description="New name for restored VM/container (None = original name)")
    overwrite: bool = Field(False, description="Whether to overwrite existing VM/container with same name")
    storage_type: str = Field("auto", description="Storage type: auto (detect from backup), file, or rbd")
    storage_config: Optional[dict] = Field(None, description="Optional storage-specific configuration override")


@router.post("/{backup_id}/restore", status_code=status.HTTP_202_ACCEPTED)
async def restore_backup(
    backup_id: int,
    request: RestoreBackupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """
    Restore a backup to a KVM host.

    The restore operation is queued as a background job and processed asynchronously.
    You can monitor the progress via the /jobs endpoint.
    """
    backup = await db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )

    if backup.status != BackupStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot restore backup with status: {backup.status}. Only completed backups can be restored."
        )

    # Validate target host if specified
    if request.target_host_id:
        if backup.source_type == SourceType.VM:
            from backend.models.infrastructure import KVMHost
            target_host = await db.get(KVMHost, request.target_host_id)
            if not target_host:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"KVM host with ID {request.target_host_id} not found"
                )
        elif backup.source_type == SourceType.CONTAINER:
            from backend.models.infrastructure import PodmanHost
            target_host = await db.get(PodmanHost, request.target_host_id)
            if not target_host:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Podman host with ID {request.target_host_id} not found"
                )

    # Queue restore job via Celery
    from backend.worker import execute_restore
    task = execute_restore.delay(
        backup_id,
        request.target_host_id,
        request.new_name,
        request.overwrite,
        request.storage_type,
        request.storage_config
    )

    # Create job record
    from backend.models.backup import Job, JobType, JobStatus
    job = Job(
        type=JobType.RESTORE,
        status=JobStatus.PENDING,
        backup_id=backup_id,
        celery_task_id=task.id,
        job_metadata={
            "target_host_id": request.target_host_id,
            "new_name": request.new_name,
            "overwrite": request.overwrite,
            "storage_type": request.storage_type,
            "storage_config": request.storage_config,
            "triggered_by": current_user.username,
            "triggered_at": datetime.utcnow().isoformat()
        }
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {
        "message": "Restore job queued successfully",
        "job_id": job.id,
        "backup_id": backup_id,
        "task_id": task.id
    }


@router.post("/{backup_id}/verify", status_code=status.HTTP_202_ACCEPTED)
async def verify_backup_endpoint(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """
    Verify a backup by restoring it to an isolated test pod.

    This endpoint triggers automated backup verification using a temporary
    PostgreSQL container. The verification process:
    1. Downloads the backup from storage
    2. Spins up an isolated test pod
    3. Restores the backup to the test database
    4. Validates the restoration (table count, database size, integrity)
    5. Tears down the test environment
    6. Updates the backup record with verification results

    The verification job is processed asynchronously. You can monitor
    progress via the /jobs endpoint.

    Returns:
        Job details including job_id and task_id for tracking
    """
    backup = await db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )

    if backup.status != BackupStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot verify backup with status: {backup.status}. Only completed backups can be verified."
        )

    # Queue verification job via Celery
    from backend.worker import verify_backup
    task = verify_backup.delay(backup_id)

    # Job will be created by the worker task itself
    # Return immediately with task info

    return {
        "message": "Backup verification job queued successfully",
        "backup_id": backup_id,
        "task_id": task.id,
        "status": "Verification in progress - check backup verification_status for results"
    }


# ============================================================================
# Immutability Management Endpoints (Issue #13)
# ============================================================================

class MakeImmutableRequest(BaseModel):
    """Request model for making a backup immutable."""
    retention_days: int = Field(..., description="Number of days to retain (0 for indefinite with LEGAL_HOLD)")
    retention_mode: str = Field("COMPLIANCE", description="Retention mode: GOVERNANCE, COMPLIANCE, or LEGAL_HOLD")
    reason: Optional[str] = Field(None, description="Human-readable reason for immutability")


@router.post("/{backup_id}/immutable", status_code=status.HTTP_200_OK)
async def make_backup_immutable(
    backup_id: int,
    request: MakeImmutableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """
    Mark a backup as immutable with retention policy.

    Admin-only endpoint. Once a backup is made immutable, it cannot be deleted
    until the retention period expires (or indefinitely for LEGAL_HOLD).

    Retention modes:
    - GOVERNANCE: Admin can override deletion
    - COMPLIANCE: Cannot delete until retention expires
    - LEGAL_HOLD: Indefinite retention, must remove hold first

    Related: Issue #13 - Immutable Backup Support
    """
    from backend.services.immutability import ImmutabilityService, ImmutabilityError
    from backend.models.backup import RetentionMode

    backup = await db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )

    # Validate retention mode
    try:
        retention_mode_enum = RetentionMode(request.retention_mode)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid retention_mode: {request.retention_mode}. "
                   "Must be GOVERNANCE, COMPLIANCE, or LEGAL_HOLD"
        )

    immutability_service = ImmutabilityService(db)

    try:
        await immutability_service.make_backup_immutable(
            backup,
            retention_days=request.retention_days,
            retention_mode=retention_mode_enum,
            reason=request.reason
        )
        await db.commit()
        await db.refresh(backup)

        return {
            "message": f"Backup {backup_id} marked as immutable",
            "backup_id": backup_id,
            "retention_mode": backup.retention_mode,
            "retention_until": backup.retention_until.isoformat() if backup.retention_until else None,
            "immutability_reason": backup.immutability_reason
        }

    except ImmutabilityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{backup_id}/legal-hold", status_code=status.HTTP_200_OK)
async def remove_legal_hold(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """
    Remove legal hold from a backup and convert to COMPLIANCE mode.

    Admin-only endpoint. Removes indefinite retention and sets a
    standard retention period based on the backup schedule configuration.

    Related: Issue #13 - Immutable Backup Support
    """
    from backend.services.immutability import ImmutabilityService, ImmutabilityError

    backup = await db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )

    immutability_service = ImmutabilityService(db)

    try:
        await immutability_service.remove_legal_hold(backup_id)
        await db.commit()
        await db.refresh(backup)

        return {
            "message": f"Legal hold removed from backup {backup_id}",
            "backup_id": backup_id,
            "retention_mode": backup.retention_mode,
            "retention_until": backup.retention_until.isoformat() if backup.retention_until else None
        }

    except ImmutabilityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/immutable/statistics")
async def get_immutability_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get statistics about immutable backups.

    Returns counts for each retention mode and expiry status.

    Related: Issue #13 - Immutable Backup Support
    """
    from backend.services.immutability import ImmutabilityService

    immutability_service = ImmutabilityService(db)
    stats = await immutability_service.get_retention_statistics()

    return stats


# ============================================================================
# Backup Chain Management Endpoints (Issue #10)
# ============================================================================

@router.get("/chains/{chain_id}")
async def get_backup_chain(
    chain_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all backups in a chain, ordered by sequence.

    Returns the full backup chain including:
    - Full backup (sequence 0)
    - All incremental backups in order
    - Deduplication and compression metrics
    """
    from backend.services.backup_chain import BackupChainService

    chain_service = BackupChainService(db)
    backups = await chain_service.get_backup_chain(chain_id)

    if not backups:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chain {chain_id} not found"
        )

    return {
        "chain_id": chain_id,
        "backup_count": len(backups),
        "backups": [BackupResponse.from_orm(b) for b in backups]
    }


@router.get("/chains/{chain_id}/statistics")
async def get_chain_statistics(
    chain_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed statistics for a backup chain.

    Includes:
    - Total storage metrics (original, compressed, saved)
    - Average deduplication and compression ratios
    - Per-backup details with sequence information
    """
    from backend.services.backup_chain import BackupChainService

    chain_service = BackupChainService(db)
    stats = await chain_service.get_chain_statistics(chain_id)

    if "error" in stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=stats["error"]
        )

    return stats


@router.get("/orphaned")
async def get_orphaned_backups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """
    Find orphaned backups (parent was deleted).

    Admin-only endpoint to identify backups whose parent_backup_id
    references a non-existent backup. These should be investigated
    and potentially cleaned up.
    """
    from backend.services.backup_chain import BackupChainService

    chain_service = BackupChainService(db)
    orphaned = await chain_service.find_orphaned_backups()

    return {
        "orphaned_count": len(orphaned),
        "backups": [BackupResponse.from_orm(b) for b in orphaned]
    }


@router.get("/statistics/global")
async def get_global_backup_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get global backup storage statistics.

    Provides system-wide metrics:
    - Total backups and chains
    - Total storage (original vs compressed)
    - Total space saved from dedup + compression
    - Average efficiency ratios
    - Overall storage efficiency percentage
    """
    from backend.services.backup_chain import BackupChainService

    chain_service = BackupChainService(db)
    stats = await chain_service.get_global_statistics()

    return stats


@router.delete("/{backup_id}/check")
async def check_backup_deletion(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OPERATOR))
):
    """
    Check if a backup can be safely deleted.

    Returns whether the backup has dependent incremental backups
    that would be orphaned if this backup is deleted.

    This is a read-only check - it does not delete anything.
    """
    from backend.services.backup_chain import BackupChainService

    chain_service = BackupChainService(db)
    can_delete, reason = await chain_service.can_delete_backup(backup_id)

    return {
        "backup_id": backup_id,
        "can_delete": can_delete,
        "reason": reason
    }
