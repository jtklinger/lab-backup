"""
QEMU Guest Agent service for application-consistent backups.

Provides filesystem freezing, script execution, and application-aware
backup operations via qemu-guest-agent.

Requires qemu-guest-agent installed and running in the guest VM.

Related: Issue #14 - Integrate QEMU Guest Agent for application consistency
"""

import logging
import json
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import libvirt

logger = logging.getLogger(__name__)


class GuestAgentError(Exception):
    """Exception raised for guest agent errors."""
    pass


class GuestAgentTimeout(Exception):
    """Exception raised when guest agent operation times out."""
    pass


class FreezeStatus:
    """Filesystem freeze status constants."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class GuestAgentService:
    """
    Service for interacting with QEMU Guest Agent.

    Provides methods for:
    - Guest agent detection and status checking
    - Filesystem freeze/thaw operations
    - Script execution in guest
    - Database-aware backup coordination
    """

    def __init__(self, domain: libvirt.virDomain):
        """
        Initialize guest agent service for a VM domain.

        Args:
            domain: Libvirt domain object
        """
        self.domain = domain
        self.guest_agent_available: Optional[bool] = None
        self.last_check_time: Optional[datetime] = None

    def is_guest_agent_available(self, force_check: bool = False) -> bool:
        """
        Check if guest agent is available and responsive.

        Args:
            force_check: Force a new check even if recently checked

        Returns:
            True if guest agent is available and responsive
        """
        # Use cached result if checked recently (within 5 minutes)
        if (
            not force_check
            and self.guest_agent_available is not None
            and self.last_check_time
            and datetime.utcnow() - self.last_check_time < timedelta(minutes=5)
        ):
            return self.guest_agent_available

        try:
            # Try to ping the guest agent
            command = {"execute": "guest-ping"}
            result = self._execute_guest_agent_command(command, timeout=5)

            # If we get a response, guest agent is available
            self.guest_agent_available = True
            self.last_check_time = datetime.utcnow()

            logger.info(f"Guest agent available for VM: {self.domain.name()}")
            return True

        except Exception as e:
            logger.debug(f"Guest agent not available for VM {self.domain.name()}: {e}")
            self.guest_agent_available = False
            self.last_check_time = datetime.utcnow()
            return False

    def get_guest_info(self) -> Dict[str, Any]:
        """
        Get guest operating system information.

        Returns:
            Dictionary with guest OS info

        Raises:
            GuestAgentError if guest agent is not available
        """
        if not self.is_guest_agent_available():
            raise GuestAgentError("Guest agent not available")

        try:
            command = {"execute": "guest-get-osinfo"}
            result = self._execute_guest_agent_command(command)

            return result.get("return", {})

        except Exception as e:
            logger.error(f"Failed to get guest info: {e}")
            raise GuestAgentError(f"Failed to get guest info: {e}")

    def freeze_filesystem(self, timeout_seconds: int = 30) -> int:
        """
        Freeze guest filesystems for consistent backup.

        This uses the guest-fsfreeze-freeze command which:
        - Flushes cached data to disk
        - Freezes all mounted filesystems
        - Ensures no writes occur during snapshot

        Args:
            timeout_seconds: Maximum time to wait for freeze

        Returns:
            Number of filesystems frozen

        Raises:
            GuestAgentError if freeze fails
            GuestAgentTimeout if freeze times out
        """
        if not self.is_guest_agent_available():
            raise GuestAgentError("Guest agent not available")

        try:
            logger.info(f"Freezing filesystems for VM: {self.domain.name()}")

            command = {"execute": "guest-fsfreeze-freeze"}
            result = self._execute_guest_agent_command(command, timeout=timeout_seconds)

            frozen_count = result.get("return", 0)

            logger.info(f"Frozen {frozen_count} filesystems for VM: {self.domain.name()}")

            return frozen_count

        except GuestAgentTimeout:
            logger.error(f"Filesystem freeze timed out after {timeout_seconds}s")
            # Attempt to thaw in case of partial freeze
            try:
                self.thaw_filesystem()
            except Exception:
                pass
            raise

        except Exception as e:
            logger.error(f"Failed to freeze filesystems: {e}")
            raise GuestAgentError(f"Failed to freeze filesystems: {e}")

    def thaw_filesystem(self) -> int:
        """
        Thaw (unfreeze) guest filesystems.

        This should always be called after freeze, even if snapshot fails.

        Returns:
            Number of filesystems thawed

        Raises:
            GuestAgentError if thaw fails
        """
        try:
            logger.info(f"Thawing filesystems for VM: {self.domain.name()}")

            command = {"execute": "guest-fsfreeze-thaw"}
            result = self._execute_guest_agent_command(command, timeout=10)

            thawed_count = result.get("return", 0)

            logger.info(f"Thawed {thawed_count} filesystems for VM: {self.domain.name()}")

            return thawed_count

        except Exception as e:
            logger.error(f"Failed to thaw filesystems: {e}")
            raise GuestAgentError(f"Failed to thaw filesystems: {e}")

    def get_fsfreeze_status(self) -> str:
        """
        Get current filesystem freeze status.

        Returns:
            "frozen" or "thawed"
        """
        try:
            command = {"execute": "guest-fsfreeze-status"}
            result = self._execute_guest_agent_command(command)

            status = result.get("return", "unknown")
            return status

        except Exception as e:
            logger.debug(f"Failed to get freeze status: {e}")
            return "unknown"

    def execute_script(
        self,
        script_content: str,
        timeout_seconds: int = 60,
        script_type: str = "bash"
    ) -> Dict[str, Any]:
        """
        Execute a script in the guest via guest agent.

        Args:
            script_content: Script content to execute
            timeout_seconds: Maximum execution time
            script_type: Script interpreter (bash, sh, python, etc.)

        Returns:
            Dictionary with execution results:
            - exitcode: Script exit code
            - stdout: Standard output
            - stderr: Standard error
            - execution_time: Time taken in seconds

        Raises:
            GuestAgentError if execution fails
            GuestAgentTimeout if script times out
        """
        if not self.is_guest_agent_available():
            raise GuestAgentError("Guest agent not available")

        if not script_content or not script_content.strip():
            logger.debug("Empty script, skipping execution")
            return {"exitcode": 0, "stdout": "", "stderr": "", "execution_time": 0}

        try:
            logger.info(f"Executing {script_type} script in guest VM: {self.domain.name()}")

            start_time = time.time()

            # Use guest-exec to run the script
            # Create a temporary file with the script content
            command = {
                "execute": "guest-exec",
                "arguments": {
                    "path": "/bin/bash",
                    "arg": ["-c", script_content],
                    "capture-output": True
                }
            }

            result = self._execute_guest_agent_command(command, timeout=5)
            pid = result.get("return", {}).get("pid")

            if not pid:
                raise GuestAgentError("Failed to start script execution")

            # Poll for completion
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                status_command = {
                    "execute": "guest-exec-status",
                    "arguments": {"pid": pid}
                }

                status = self._execute_guest_agent_command(status_command, timeout=5)
                status_result = status.get("return", {})

                if status_result.get("exited", False):
                    execution_time = time.time() - start_time

                    # Get output
                    import base64
                    stdout_b64 = status_result.get("out-data", "")
                    stderr_b64 = status_result.get("err-data", "")

                    stdout = base64.b64decode(stdout_b64).decode("utf-8", errors="replace") if stdout_b64 else ""
                    stderr = base64.b64decode(stderr_b64).decode("utf-8", errors="replace") if stderr_b64 else ""

                    exitcode = status_result.get("exitcode", -1)

                    logger.info(
                        f"Script execution completed: exitcode={exitcode}, "
                        f"time={execution_time:.2f}s"
                    )

                    return {
                        "exitcode": exitcode,
                        "stdout": stdout,
                        "stderr": stderr,
                        "execution_time": execution_time
                    }

                # Wait before polling again
                time.sleep(0.5)

            # Timeout reached
            execution_time = time.time() - start_time
            raise GuestAgentTimeout(
                f"Script execution timed out after {execution_time:.2f}s"
            )

        except GuestAgentTimeout:
            raise

        except Exception as e:
            logger.error(f"Failed to execute script: {e}")
            raise GuestAgentError(f"Failed to execute script: {e}")

    def _execute_guest_agent_command(
        self,
        command: Dict[str, Any],
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Execute a guest agent command via QGA (QEMU Guest Agent).

        Args:
            command: QGA command dictionary
            timeout: Command timeout in seconds

        Returns:
            QGA response dictionary

        Raises:
            GuestAgentError if command fails
            GuestAgentTimeout if command times out
        """
        try:
            # Convert command to JSON
            command_json = json.dumps(command)

            # Execute via qemuAgentCommand
            # flags: VIR_DOMAIN_QEMU_AGENT_COMMAND_DEFAULT = 0
            result_json = self.domain.qemuAgentCommand(
                command_json,
                timeout=timeout,
                flags=0
            )

            # Parse response
            result = json.loads(result_json)

            if "error" in result:
                error_msg = result["error"].get("desc", "Unknown error")
                raise GuestAgentError(f"Guest agent command failed: {error_msg}")

            return result

        except libvirt.libvirtError as e:
            error_msg = str(e)
            if "Guest agent is not responding" in error_msg or "not connected" in error_msg:
                raise GuestAgentError("Guest agent not responding")
            elif "timeout" in error_msg.lower():
                raise GuestAgentTimeout(f"Guest agent command timed out after {timeout}s")
            else:
                raise GuestAgentError(f"Libvirt error: {error_msg}")

        except json.JSONDecodeError as e:
            raise GuestAgentError(f"Invalid JSON response from guest agent: {e}")

        except Exception as e:
            raise GuestAgentError(f"Guest agent command failed: {e}")


class DatabaseBackupScripts:
    """
    Pre-built scripts for database-aware backups.

    Provides scripts for common databases to ensure consistent backups.
    """

    @staticmethod
    def mysql_pre_backup() -> str:
        """
        MySQL pre-backup script.

        Flushes tables and acquires read lock to ensure consistency.
        """
        return """#!/bin/bash
# MySQL Pre-Backup Script
# Ensures database consistency before backup

if command -v mysql >/dev/null 2>&1; then
    echo "Flushing MySQL tables..."
    mysql -e "FLUSH TABLES WITH READ LOCK; SYSTEM sleep 2" 2>&1
    echo "MySQL prepared for backup"
else
    echo "MySQL not found, skipping"
fi
"""

    @staticmethod
    def mysql_post_backup() -> str:
        """
        MySQL post-backup script.

        Releases read lock after backup completes.
        """
        return """#!/bin/bash
# MySQL Post-Backup Script
# Releases locks after backup

if command -v mysql >/dev/null 2>&1; then
    echo "Unlocking MySQL tables..."
    mysql -e "UNLOCK TABLES" 2>&1
    echo "MySQL resumed normal operations"
else
    echo "MySQL not found, skipping"
fi
"""

    @staticmethod
    def postgresql_pre_backup() -> str:
        """
        PostgreSQL pre-backup script.

        Starts backup mode to ensure WAL consistency.
        """
        return """#!/bin/bash
# PostgreSQL Pre-Backup Script
# Starts backup mode for consistency

if command -v psql >/dev/null 2>&1; then
    echo "Starting PostgreSQL backup mode..."
    sudo -u postgres psql -c "SELECT pg_start_backup('lab-backup', false, false);" 2>&1
    echo "PostgreSQL backup mode started"
else
    echo "PostgreSQL not found, skipping"
fi
"""

    @staticmethod
    def postgresql_post_backup() -> str:
        """
        PostgreSQL post-backup script.

        Stops backup mode and returns to normal operations.
        """
        return """#!/bin/bash
# PostgreSQL Post-Backup Script
# Stops backup mode

if command -v psql >/dev/null 2>&1; then
    echo "Stopping PostgreSQL backup mode..."
    sudo -u postgres psql -c "SELECT pg_stop_backup();" 2>&1
    echo "PostgreSQL backup mode stopped"
else
    echo "PostgreSQL not found, skipping"
fi
"""

    @staticmethod
    def mongodb_pre_backup() -> str:
        """
        MongoDB pre-backup script.

        Locks MongoDB to ensure consistent backup.
        """
        return """#!/bin/bash
# MongoDB Pre-Backup Script
# Locks database for consistency

if command -v mongo >/dev/null 2>&1; then
    echo "Locking MongoDB..."
    mongo --eval "db.fsyncLock()" 2>&1
    echo "MongoDB locked for backup"
else
    echo "MongoDB not found, skipping"
fi
"""

    @staticmethod
    def mongodb_post_backup() -> str:
        """
        MongoDB post-backup script.

        Unlocks MongoDB after backup.
        """
        return """#!/bin/bash
# MongoDB Post-Backup Script
# Unlocks database

if command -v mongo >/dev/null 2>&1; then
    echo "Unlocking MongoDB..."
    mongo --eval "db.fsyncUnlock()" 2>&1
    echo "MongoDB unlocked"
else
    echo "MongoDB not found, skipping"
fi
"""
