"""
Compliance tracking service for backup coverage monitoring.

Implements HYCU-style state machine for backup compliance:
- GREY: No backup policy assigned or VM excluded
- GREEN: Fully compliant (backups within RPO)
- YELLOW: Warning state (backup aging, minor issues)
- RED: Non-compliant (no backups, RPO exceeded)

Related: Issue #8 - Build Compliance Tracking System
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.infrastructure import VM, Container
from backend.models.backup import BackupSchedule, Backup, BackupStatus, SourceType
from backend.core.logging import logger


class ComplianceStatus:
    """Compliance status constants."""
    GREY = "GREY"
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class ComplianceService:
    """Service for calculating and tracking backup compliance status."""

    def __init__(self, db: AsyncSession):
        """
        Initialize compliance service.

        Args:
            db: Database session
        """
        self.db = db

    async def calculate_vm_compliance(self, vm_id: int) -> Tuple[str, str]:
        """
        Calculate compliance status for a VM.

        Args:
            vm_id: VM ID

        Returns:
            Tuple of (status, reason)
            - status: GREY/GREEN/YELLOW/RED
            - reason: Human-readable explanation
        """
        # Get VM with backup schedule
        stmt = select(VM).where(VM.id == vm_id)
        result = await self.db.execute(stmt)
        vm = result.scalar_one_or_none()

        if not vm:
            return ComplianceStatus.GREY, f"VM not found (ID: {vm_id})"

        # Check if VM has backup schedules
        schedule_stmt = select(BackupSchedule).where(
            and_(
                BackupSchedule.source_type == SourceType.VM,
                BackupSchedule.source_id == vm_id,
                BackupSchedule.enabled == True
            )
        )
        schedule_result = await self.db.execute(schedule_stmt)
        schedules = schedule_result.scalars().all()

        if not schedules:
            return ComplianceStatus.GREY, "No active backup schedule assigned"

        # Check for successful backups
        backup_stmt = select(Backup).where(
            and_(
                Backup.source_type == SourceType.VM,
                Backup.source_id == vm_id,
                Backup.status == BackupStatus.COMPLETED
            )
        ).order_by(Backup.completed_at.desc()).limit(1)

        backup_result = await self.db.execute(backup_stmt)
        last_backup = backup_result.scalar_one_or_none()

        if not last_backup or not last_backup.completed_at:
            return ComplianceStatus.RED, "No successful backups found"

        # Get most restrictive RPO from schedules
        min_rpo_minutes = None
        for schedule in schedules:
            if schedule.rpo_minutes is not None:
                if min_rpo_minutes is None:
                    min_rpo_minutes = schedule.rpo_minutes
                else:
                    min_rpo_minutes = min(min_rpo_minutes, schedule.rpo_minutes)

        if min_rpo_minutes is None:
            # No RPO configured, use default threshold
            min_rpo_minutes = 1440  # 24 hours default

        # Calculate time since last successful backup
        now = datetime.utcnow()
        time_since_backup = now - last_backup.completed_at
        minutes_since_backup = int(time_since_backup.total_seconds() / 60)

        # Apply state machine logic
        if minutes_since_backup <= min_rpo_minutes:
            return ComplianceStatus.GREEN, f"Compliant - Last backup {minutes_since_backup}m ago (RPO: {min_rpo_minutes}m)"

        # Calculate threshold for YELLOW (warning at 80% of RPO exceeded)
        yellow_threshold = min_rpo_minutes * 1.2  # 20% grace period

        if minutes_since_backup <= yellow_threshold:
            overage = minutes_since_backup - min_rpo_minutes
            return ComplianceStatus.YELLOW, f"Warning - RPO exceeded by {overage}m (Last backup: {minutes_since_backup}m ago, RPO: {min_rpo_minutes}m)"

        # RED: Severely out of compliance
        overage = minutes_since_backup - min_rpo_minutes
        return ComplianceStatus.RED, f"Non-compliant - RPO exceeded by {overage}m (Last backup: {minutes_since_backup}m ago, RPO: {min_rpo_minutes}m)"

    async def calculate_container_compliance(self, container_id: int) -> Tuple[str, str]:
        """
        Calculate compliance status for a container.

        Args:
            container_id: Container ID

        Returns:
            Tuple of (status, reason)
        """
        # Get Container with backup schedule
        stmt = select(Container).where(Container.id == container_id)
        result = await self.db.execute(stmt)
        container = result.scalar_one_or_none()

        if not container:
            return ComplianceStatus.GREY, f"Container not found (ID: {container_id})"

        # Check if container has backup schedules
        schedule_stmt = select(BackupSchedule).where(
            and_(
                BackupSchedule.source_type == SourceType.CONTAINER,
                BackupSchedule.source_id == container_id,
                BackupSchedule.enabled == True
            )
        )
        schedule_result = await self.db.execute(schedule_stmt)
        schedules = schedule_result.scalars().all()

        if not schedules:
            return ComplianceStatus.GREY, "No active backup schedule assigned"

        # Check for successful backups
        backup_stmt = select(Backup).where(
            and_(
                Backup.source_type == SourceType.CONTAINER,
                Backup.source_id == container_id,
                Backup.status == BackupStatus.COMPLETED
            )
        ).order_by(Backup.completed_at.desc()).limit(1)

        backup_result = await self.db.execute(backup_stmt)
        last_backup = backup_result.scalar_one_or_none()

        if not last_backup or not last_backup.completed_at:
            return ComplianceStatus.RED, "No successful backups found"

        # Get most restrictive RPO from schedules
        min_rpo_minutes = None
        for schedule in schedules:
            if schedule.rpo_minutes is not None:
                if min_rpo_minutes is None:
                    min_rpo_minutes = schedule.rpo_minutes
                else:
                    min_rpo_minutes = min(min_rpo_minutes, schedule.rpo_minutes)

        if min_rpo_minutes is None:
            # No RPO configured, use default threshold
            min_rpo_minutes = 1440  # 24 hours default

        # Calculate time since last successful backup
        now = datetime.utcnow()
        time_since_backup = now - last_backup.completed_at
        minutes_since_backup = int(time_since_backup.total_seconds() / 60)

        # Apply state machine logic
        if minutes_since_backup <= min_rpo_minutes:
            return ComplianceStatus.GREEN, f"Compliant - Last backup {minutes_since_backup}m ago (RPO: {min_rpo_minutes}m)"

        # Calculate threshold for YELLOW (warning at 20% grace period)
        yellow_threshold = min_rpo_minutes * 1.2

        if minutes_since_backup <= yellow_threshold:
            overage = minutes_since_backup - min_rpo_minutes
            return ComplianceStatus.YELLOW, f"Warning - RPO exceeded by {overage}m (Last backup: {minutes_since_backup}m ago, RPO: {min_rpo_minutes}m)"

        # RED: Severely out of compliance
        overage = minutes_since_backup - min_rpo_minutes
        return ComplianceStatus.RED, f"Non-compliant - RPO exceeded by {overage}m (Last backup: {minutes_since_backup}m ago, RPO: {min_rpo_minutes}m)"

    async def update_vm_compliance(self, vm_id: int) -> bool:
        """
        Calculate and update compliance status for a VM.

        Args:
            vm_id: VM ID

        Returns:
            True if updated successfully
        """
        status, reason = await self.calculate_vm_compliance(vm_id)

        stmt = select(VM).where(VM.id == vm_id)
        result = await self.db.execute(stmt)
        vm = result.scalar_one_or_none()

        if not vm:
            logger.warning(f"Cannot update compliance for non-existent VM: {vm_id}")
            return False

        old_status = vm.compliance_status
        vm.compliance_status = status
        vm.compliance_reason = reason
        vm.compliance_last_checked = datetime.utcnow()

        await self.db.commit()

        # Log status changes
        if old_status != status:
            logger.info(f"VM '{vm.name}' compliance changed: {old_status} -> {status} ({reason})")

            # Send immediate alert if transitioned to RED
            if status == ComplianceStatus.RED and old_status != ComplianceStatus.RED:
                try:
                    from backend.services.email import ComplianceEmailService
                    email_service = ComplianceEmailService()
                    await email_service.send_red_status_alert(
                        entity_type="VM",
                        entity_id=vm.id,
                        entity_name=vm.name,
                        compliance_reason=reason,
                        last_successful_backup=vm.last_successful_backup
                    )
                    logger.info(f"Sent RED status alert for VM '{vm.name}'")
                except Exception as e:
                    logger.error(f"Failed to send RED status alert for VM '{vm.name}': {e}")

        return True

    async def update_container_compliance(self, container_id: int) -> bool:
        """
        Calculate and update compliance status for a container.

        Args:
            container_id: Container ID

        Returns:
            True if updated successfully
        """
        status, reason = await self.calculate_container_compliance(container_id)

        stmt = select(Container).where(Container.id == container_id)
        result = await self.db.execute(stmt)
        container = result.scalar_one_or_none()

        if not container:
            logger.warning(f"Cannot update compliance for non-existent container: {container_id}")
            return False

        old_status = container.compliance_status
        container.compliance_status = status
        container.compliance_reason = reason
        container.compliance_last_checked = datetime.utcnow()

        await self.db.commit()

        # Log status changes
        if old_status != status:
            logger.info(f"Container '{container.name}' compliance changed: {old_status} -> {status} ({reason})")

            # Send immediate alert if transitioned to RED
            if status == ComplianceStatus.RED and old_status != ComplianceStatus.RED:
                try:
                    from backend.services.email import ComplianceEmailService
                    email_service = ComplianceEmailService()
                    await email_service.send_red_status_alert(
                        entity_type="Container",
                        entity_id=container.id,
                        entity_name=container.name,
                        compliance_reason=reason,
                        last_successful_backup=container.last_successful_backup
                    )
                    logger.info(f"Sent RED status alert for Container '{container.name}'")
                except Exception as e:
                    logger.error(f"Failed to send RED status alert for Container '{container.name}': {e}")

        return True

    async def update_last_successful_backup(
        self,
        source_type: SourceType,
        source_id: int,
        completed_at: datetime
    ) -> bool:
        """
        Update last_successful_backup timestamp when a backup completes.

        This should be called by the backup task when a backup finishes successfully.

        Args:
            source_type: VM or CONTAINER
            source_id: ID of the VM or container
            completed_at: Timestamp when backup completed

        Returns:
            True if updated successfully
        """
        if source_type == SourceType.VM:
            stmt = select(VM).where(VM.id == source_id)
            result = await self.db.execute(stmt)
            entity = result.scalar_one_or_none()
        else:
            stmt = select(Container).where(Container.id == source_id)
            result = await self.db.execute(stmt)
            entity = result.scalar_one_or_none()

        if not entity:
            logger.warning(f"Cannot update last backup for non-existent {source_type}: {source_id}")
            return False

        # Update last successful backup timestamp
        old_timestamp = entity.last_successful_backup
        entity.last_successful_backup = completed_at
        await self.db.commit()

        logger.info(
            f"{source_type.upper()} {source_id} last_successful_backup updated: "
            f"{old_timestamp} -> {completed_at}"
        )

        return True

    async def calculate_all_compliance(self) -> Dict[str, int]:
        """
        Calculate compliance for all VMs and containers.

        This is intended to be run periodically (e.g., hourly) by a Celery task.

        Returns:
            Dictionary with update counts:
            {
                'vms_updated': 10,
                'containers_updated': 5,
                'errors': 0
            }
        """
        stats = {
            'vms_updated': 0,
            'containers_updated': 0,
            'errors': 0
        }

        # Update all VMs
        vm_stmt = select(VM)
        vm_result = await self.db.execute(vm_stmt)
        vms = vm_result.scalars().all()

        for vm in vms:
            try:
                await self.update_vm_compliance(vm.id)
                stats['vms_updated'] += 1
            except Exception as e:
                logger.error(f"Error updating compliance for VM {vm.id}: {e}")
                stats['errors'] += 1

        # Update all containers
        container_stmt = select(Container)
        container_result = await self.db.execute(container_stmt)
        containers = container_result.scalars().all()

        for container in containers:
            try:
                await self.update_container_compliance(container.id)
                stats['containers_updated'] += 1
            except Exception as e:
                logger.error(f"Error updating compliance for container {container.id}: {e}")
                stats['errors'] += 1

        logger.info(f"Compliance calculation completed: {stats}")
        return stats

    async def get_compliance_dashboard(self) -> Dict[str, Any]:
        """
        Get compliance overview dashboard data.

        Returns:
            Dictionary with compliance statistics:
            {
                'vms': {
                    'total': 100,
                    'grey': 10,
                    'green': 70,
                    'yellow': 15,
                    'red': 5
                },
                'containers': {...},
                'last_updated': '2025-11-17T23:45:00Z'
            }
        """
        # VM compliance breakdown
        vm_total_stmt = select(func.count(VM.id))
        vm_total_result = await self.db.execute(vm_total_stmt)
        vm_total = vm_total_result.scalar() or 0

        vm_stats = {
            'total': vm_total,
            'grey': 0,
            'green': 0,
            'yellow': 0,
            'red': 0
        }

        for status in [ComplianceStatus.GREY, ComplianceStatus.GREEN,
                       ComplianceStatus.YELLOW, ComplianceStatus.RED]:
            stmt = select(func.count(VM.id)).where(VM.compliance_status == status)
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            vm_stats[status.lower()] = count

        # Container compliance breakdown
        container_total_stmt = select(func.count(Container.id))
        container_total_result = await self.db.execute(container_total_stmt)
        container_total = container_total_result.scalar() or 0

        container_stats = {
            'total': container_total,
            'grey': 0,
            'green': 0,
            'yellow': 0,
            'red': 0
        }

        for status in [ComplianceStatus.GREY, ComplianceStatus.GREEN,
                       ComplianceStatus.YELLOW, ComplianceStatus.RED]:
            stmt = select(func.count(Container.id)).where(Container.compliance_status == status)
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            container_stats[status.lower()] = count

        # Get most recent compliance check timestamp
        vm_last_checked_stmt = select(VM.compliance_last_checked).order_by(
            VM.compliance_last_checked.desc()
        ).limit(1)
        vm_last_result = await self.db.execute(vm_last_checked_stmt)
        vm_last_checked = vm_last_result.scalar_one_or_none()

        container_last_checked_stmt = select(Container.compliance_last_checked).order_by(
            Container.compliance_last_checked.desc()
        ).limit(1)
        container_last_result = await self.db.execute(container_last_checked_stmt)
        container_last_checked = container_last_result.scalar_one_or_none()

        last_updated = None
        if vm_last_checked and container_last_checked:
            last_updated = max(vm_last_checked, container_last_checked)
        elif vm_last_checked:
            last_updated = vm_last_checked
        elif container_last_checked:
            last_updated = container_last_checked

        return {
            'vms': vm_stats,
            'containers': container_stats,
            'last_updated': last_updated.isoformat() if last_updated else None
        }

    async def get_non_compliant_entities(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all non-compliant (RED) VMs and containers.

        Useful for alerting and reporting.

        Returns:
            Dictionary with lists of non-compliant entities:
            {
                'vms': [
                    {'id': 1, 'name': 'web-server', 'reason': '...'},
                    ...
                ],
                'containers': [...]
            }
        """
        # Get RED VMs
        vm_stmt = select(VM).where(VM.compliance_status == ComplianceStatus.RED)
        vm_result = await self.db.execute(vm_stmt)
        red_vms = vm_result.scalars().all()

        # Get RED containers
        container_stmt = select(Container).where(
            Container.compliance_status == ComplianceStatus.RED
        )
        container_result = await self.db.execute(container_stmt)
        red_containers = container_result.scalars().all()

        return {
            'vms': [
                {
                    'id': vm.id,
                    'name': vm.name,
                    'reason': vm.compliance_reason,
                    'last_backup': vm.last_successful_backup.isoformat() if vm.last_successful_backup else None,
                    'last_checked': vm.compliance_last_checked.isoformat() if vm.compliance_last_checked else None
                }
                for vm in red_vms
            ],
            'containers': [
                {
                    'id': container.id,
                    'name': container.name,
                    'reason': container.compliance_reason,
                    'last_backup': container.last_successful_backup.isoformat() if container.last_successful_backup else None,
                    'last_checked': container.compliance_last_checked.isoformat() if container.compliance_last_checked else None
                }
                for container in red_containers
            ]
        }
