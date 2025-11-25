"""
WebSocket endpoints for real-time job log streaming.
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import AsyncSessionLocal
from backend.models.user import User, UserRole
from backend.models.backup import Job, JobLog, JobStatus
from backend.core.security import get_current_user_from_token

router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections per job."""

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: int):
        """Accept and track a new WebSocket connection."""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: int):
        """Remove a WebSocket connection."""
        if job_id in self.active_connections:
            if websocket in self.active_connections[job_id]:
                self.active_connections[job_id].remove(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

    async def broadcast_to_job(self, job_id: int, message: dict):
        """Broadcast message to all connections watching a job."""
        if job_id in self.active_connections:
            disconnected = []
            for websocket in self.active_connections[job_id]:
                try:
                    await websocket.send_json(message)
                except Exception:
                    disconnected.append(websocket)
            # Clean up disconnected
            for ws in disconnected:
                self.disconnect(ws, job_id)


manager = ConnectionManager()


def serialize_log(log: JobLog) -> dict:
    """Serialize a JobLog to dict for JSON transmission."""
    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "level": log.level,
        "message": log.message,
        "details": log.details,
    }


@router.websocket("/ws/jobs/{job_id}")
async def job_logs_websocket(
    websocket: WebSocket,
    job_id: int,
    token: str = Query(...)
):
    """
    WebSocket endpoint for real-time job log streaming.

    Connect with: ws://host/api/v1/ws/jobs/{job_id}?token={jwt_token}

    Messages sent:
    - type: "log" - New log entry
    - type: "status" - Job status update
    - type: "error" - Error message
    - type: "connected" - Initial connection confirmation
    - type: "complete" - Job has completed
    """
    # Validate token and check permissions
    async with AsyncSessionLocal() as db:
        user = await get_current_user_from_token(token, db)

        if not user:
            await websocket.close(code=4001, reason="Invalid token")
            return

        if user.role not in [UserRole.ADMIN, UserRole.OPERATOR]:
            await websocket.close(code=4003, reason="Insufficient permissions")
            return

        # Check job exists
        job = await db.get(Job, job_id)
        if not job:
            await websocket.close(code=4004, reason="Job not found")
            return

    # Accept connection
    await manager.connect(websocket, job_id)

    # Track state for polling
    last_log_id = 0
    last_status = job.status

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "job_id": job_id,
            "status": job.status.value,
            "message": f"Connected to job {job_id} logs"
        })

        # Send existing logs
        stmt = select(JobLog).where(JobLog.job_id == job_id).order_by(JobLog.timestamp)
        result = await db.execute(stmt)
        existing_logs = result.scalars().all()

        for log in existing_logs:
            await websocket.send_json({
                "type": "log",
                "data": serialize_log(log)
            })

        if existing_logs:
            last_log_id = existing_logs[-1].id

        # If job is already completed, send complete message and close
        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            await websocket.send_json({
                "type": "complete",
                "status": job.status.value,
                "message": f"Job {job.status.value}"
            })
            return

        # Poll for new logs while job is running
        while True:
            await asyncio.sleep(1)  # Poll every second

            async with AsyncSessionLocal() as poll_db:
                # Check for new logs
                stmt = (
                    select(JobLog)
                    .where(JobLog.job_id == job_id)
                    .where(JobLog.id > last_log_id)
                    .order_by(JobLog.timestamp)
                )
                result = await poll_db.execute(stmt)
                new_logs = result.scalars().all()

                for log in new_logs:
                    await websocket.send_json({
                        "type": "log",
                        "data": serialize_log(log)
                    })
                    last_log_id = log.id

                # Check job status
                current_job = await poll_db.get(Job, job_id)
                if current_job.status != last_status:
                    last_status = current_job.status
                    await websocket.send_json({
                        "type": "status",
                        "status": current_job.status.value
                    })

                # If job completed, send complete message and close
                if current_job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    await websocket.send_json({
                        "type": "complete",
                        "status": current_job.status.value,
                        "message": f"Job {current_job.status.value}"
                    })
                    break

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, job_id)
