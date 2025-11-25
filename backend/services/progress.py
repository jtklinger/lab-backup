"""
Job progress tracking service for real-time backup progress monitoring.

Provides:
- Per-disk progress tracking with bytes transferred
- Overall job progress aggregation
- ETA calculation based on transfer rates
- Thread-safe progress updates
- Periodic database persistence
"""

import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class DiskProgress:
    """Progress tracking for a single disk."""
    target: str
    disk_type: str  # 'file' or 'rbd'
    status: str = "pending"  # pending, transferring, completed, failed
    bytes_transferred: int = 0
    bytes_total: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    _samples: List[tuple] = field(default_factory=list)  # (timestamp, bytes) for rate calc

    @property
    def percent(self) -> float:
        if self.bytes_total <= 0:
            return 0.0
        return min(100.0, (self.bytes_transferred / self.bytes_total) * 100)

    @property
    def transfer_rate_bps(self) -> float:
        """Calculate transfer rate in bytes per second using recent samples."""
        if len(self._samples) < 2:
            return 0.0

        # Use last 10 seconds of samples for smoothing
        now = time.time()
        recent = [(t, b) for t, b in self._samples if now - t < 10]
        if len(recent) < 2:
            recent = self._samples[-2:]

        if len(recent) < 2:
            return 0.0

        time_delta = recent[-1][0] - recent[0][0]
        bytes_delta = recent[-1][1] - recent[0][1]

        if time_delta <= 0:
            return 0.0

        return bytes_delta / time_delta

    def update(self, bytes_transferred: int, bytes_total: Optional[int] = None):
        """Update progress for this disk."""
        now = time.time()

        if self.status == "pending":
            self.status = "transferring"
            self.started_at = datetime.now(timezone.utc)

        self.bytes_transferred = bytes_transferred
        if bytes_total is not None:
            self.bytes_total = bytes_total

        # Add sample for rate calculation (keep last 20)
        self._samples.append((now, bytes_transferred))
        if len(self._samples) > 20:
            self._samples = self._samples[-20:]

        # Check if completed
        if self.bytes_total > 0 and bytes_transferred >= self.bytes_total:
            self.status = "completed"
            self.completed_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON/WebSocket transmission."""
        return {
            "target": self.target,
            "type": self.disk_type,
            "status": self.status,
            "bytes_transferred": self.bytes_transferred,
            "bytes_total": self.bytes_total,
            "percent": round(self.percent, 1),
            "transfer_rate_bps": round(self.transfer_rate_bps),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ProgressTracker:
    """
    Track progress for a single backup job.

    Thread-safe progress tracking with ETA calculation and
    periodic database persistence.
    """

    def __init__(self, job_id: int):
        self.job_id = job_id
        self._lock = threading.Lock()
        self._disks: Dict[str, DiskProgress] = {}
        self._started_at: Optional[datetime] = None
        self._current_phase: str = "preparing"
        self._last_db_update: float = 0
        self._phase_weights = {
            "preparing": 0.02,
            "disk_transfer": 0.90,
            "archiving": 0.03,
            "encrypting": 0.02,
            "uploading": 0.03,
        }

    def initialize_disks(self, disks: List[Dict[str, Any]]):
        """
        Initialize disk tracking from VM info.

        Args:
            disks: List of disk info dicts with 'target', 'size', and optionally 'type'
        """
        with self._lock:
            self._started_at = datetime.now(timezone.utc)
            for disk in disks:
                target = disk.get("target", disk.get("dev", "unknown"))
                disk_type = disk.get("type", "file")
                size = disk.get("size", disk.get("capacity", 0))

                # Normalize disk type
                if disk_type in ("network", "rbd"):
                    disk_type = "rbd"
                else:
                    disk_type = "file"

                self._disks[target] = DiskProgress(
                    target=target,
                    disk_type=disk_type,
                    bytes_total=size
                )
            logger.debug(f"Initialized progress tracker for job {self.job_id} with {len(self._disks)} disks")

    def set_phase(self, phase: str):
        """Update the current backup phase."""
        with self._lock:
            self._current_phase = phase
            logger.debug(f"Job {self.job_id} phase: {phase}")

    def update_disk(self, target: str, bytes_transferred: int, bytes_total: Optional[int] = None):
        """
        Update progress for a specific disk.

        Args:
            target: Disk target name (e.g., 'vda')
            bytes_transferred: Bytes transferred so far
            bytes_total: Total bytes to transfer (optional, updates if provided)
        """
        with self._lock:
            if target not in self._disks:
                # Auto-create disk entry if not initialized
                self._disks[target] = DiskProgress(
                    target=target,
                    disk_type="file",
                    bytes_total=bytes_total or 0
                )

            self._disks[target].update(bytes_transferred, bytes_total)

    def mark_disk_completed(self, target: str):
        """Mark a disk as completed."""
        with self._lock:
            if target in self._disks:
                disk = self._disks[target]
                disk.status = "completed"
                disk.completed_at = datetime.now(timezone.utc)
                if disk.bytes_total > 0:
                    disk.bytes_transferred = disk.bytes_total

    def mark_disk_failed(self, target: str, error: Optional[str] = None):
        """Mark a disk as failed."""
        with self._lock:
            if target in self._disks:
                self._disks[target].status = "failed"

    def get_progress(self) -> Dict[str, Any]:
        """Get current progress snapshot for WebSocket/API."""
        with self._lock:
            # Calculate overall progress
            total_bytes = sum(d.bytes_total for d in self._disks.values())
            transferred_bytes = sum(d.bytes_transferred for d in self._disks.values())

            # Calculate percent (with phase weighting for non-transfer phases)
            if self._current_phase == "disk_transfer":
                if total_bytes > 0:
                    percent = (transferred_bytes / total_bytes) * 100 * self._phase_weights["disk_transfer"]
                    percent += self._phase_weights["preparing"] * 100  # Preparing is done
                else:
                    percent = self._phase_weights["preparing"] * 100
            elif self._current_phase == "preparing":
                percent = 0.0
            else:
                # Post-transfer phases
                base_percent = (self._phase_weights["preparing"] + self._phase_weights["disk_transfer"]) * 100
                phase_order = ["archiving", "encrypting", "uploading"]
                for p in phase_order:
                    if self._current_phase == p:
                        percent = base_percent + (self._phase_weights[p] * 100 * 0.5)  # Halfway through phase
                        break
                    base_percent += self._phase_weights[p] * 100
                else:
                    percent = 100.0  # Done

            # Calculate ETA
            eta_seconds = self._calculate_eta(transferred_bytes, total_bytes)

            # Current disk index
            disks_list = list(self._disks.values())
            current_disk_index = 0
            for i, disk in enumerate(disks_list):
                if disk.status == "transferring":
                    current_disk_index = i
                    break
                elif disk.status == "pending":
                    current_disk_index = i
                    break

            return {
                "overall": {
                    "percent": round(min(100.0, percent), 1),
                    "bytes_transferred": transferred_bytes,
                    "bytes_total": total_bytes,
                    "started_at": self._started_at.isoformat() if self._started_at else None,
                    "eta_seconds": eta_seconds,
                    "current_phase": self._current_phase,
                    "current_disk_index": current_disk_index,
                    "total_disks": len(self._disks),
                },
                "disks": [d.to_dict() for d in disks_list],
            }

    def _calculate_eta(self, transferred: int, total: int) -> Optional[int]:
        """Calculate estimated time remaining in seconds."""
        if not self._started_at or total <= 0:
            return None

        if transferred >= total:
            return 0

        # Calculate overall transfer rate from all disks
        total_rate = sum(d.transfer_rate_bps for d in self._disks.values())

        if total_rate <= 0:
            # Fall back to time-based estimate
            elapsed = (datetime.now(timezone.utc) - self._started_at).total_seconds()
            if elapsed > 0 and transferred > 0:
                rate = transferred / elapsed
                remaining = total - transferred
                return int(remaining / rate)
            return None

        remaining = total - transferred
        return int(remaining / total_rate)

    async def persist_to_database(self, db):
        """
        Save progress to job_metadata in database.

        Args:
            db: AsyncSession instance
        """
        from backend.models.backup import Job

        try:
            job = await db.get(Job, self.job_id)
            if job:
                progress_data = self.get_progress()

                # Update job_metadata
                if job.job_metadata is None:
                    job.job_metadata = {}
                job.job_metadata["progress"] = progress_data

                await db.commit()
                self._last_db_update = time.time()
                logger.debug(f"Persisted progress for job {self.job_id}")
        except Exception as e:
            logger.warning(f"Failed to persist progress for job {self.job_id}: {e}")

    def should_persist(self, interval_seconds: float = 5.0) -> bool:
        """Check if enough time has passed for database persistence."""
        return time.time() - self._last_db_update >= interval_seconds


class ProgressRegistry:
    """
    Global registry for tracking progress of all active jobs.

    Singleton pattern ensures one registry across the application.
    """

    _instance: Optional["ProgressRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._trackers: Dict[int, ProgressTracker] = {}
                    cls._instance._trackers_lock = threading.Lock()
        return cls._instance

    @classmethod
    def get_instance(cls) -> "ProgressRegistry":
        """Get the singleton instance."""
        return cls()

    def get_or_create(self, job_id: int) -> ProgressTracker:
        """Get existing tracker or create a new one."""
        with self._trackers_lock:
            if job_id not in self._trackers:
                self._trackers[job_id] = ProgressTracker(job_id)
                logger.info(f"Created progress tracker for job {job_id}")
            return self._trackers[job_id]

    def get(self, job_id: int) -> Optional[ProgressTracker]:
        """Get tracker for a job, or None if not found."""
        with self._trackers_lock:
            return self._trackers.get(job_id)

    def remove(self, job_id: int) -> Optional[ProgressTracker]:
        """Remove and return tracker for a job."""
        with self._trackers_lock:
            tracker = self._trackers.pop(job_id, None)
            if tracker:
                logger.info(f"Removed progress tracker for job {job_id}")
            return tracker

    def list_active_jobs(self) -> List[int]:
        """List all job IDs with active trackers."""
        with self._trackers_lock:
            return list(self._trackers.keys())


# Module-level convenience functions
def get_progress_registry() -> ProgressRegistry:
    """Get the global progress registry instance."""
    return ProgressRegistry.get_instance()


def get_tracker(job_id: int) -> Optional[ProgressTracker]:
    """Get progress tracker for a job."""
    return get_progress_registry().get(job_id)


def create_tracker(job_id: int) -> ProgressTracker:
    """Create or get progress tracker for a job."""
    return get_progress_registry().get_or_create(job_id)


def remove_tracker(job_id: int) -> Optional[ProgressTracker]:
    """Remove progress tracker for a job."""
    return get_progress_registry().remove(job_id)
