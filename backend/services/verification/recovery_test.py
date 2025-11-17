"""
Recovery Test Service

Manages the lifecycle of isolated test pods for backup verification.
This service creates temporary PostgreSQL containers, restores backups,
verifies the restoration, and tears down the test environment.

Architecture:
- Each verification job gets a unique isolated test pod
- Test pod uses tmpfs volumes for fast I/O and automatic cleanup
- Isolated network prevents access to production systems
- Automatic cleanup on success or failure
"""

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import logging

from backend.core.config import settings
from backend.core.encryption import decrypt_backup

logger = logging.getLogger(__name__)


class RecoveryTestError(Exception):
    """Exception raised when recovery test fails."""
    pass


class RecoveryTestService:
    """
    Service for managing backup verification via isolated test pods.

    This service orchestrates the entire verification workflow:
    1. Download backup from storage
    2. Decrypt if needed
    3. Spin up isolated test pod
    4. Restore backup to test database
    5. Run verification queries
    6. Collect metrics
    7. Tear down test pod
    8. Return verification results
    """

    def __init__(self, job_id: int):
        """
        Initialize recovery test service.

        Args:
            job_id: Unique job ID for this verification run
        """
        self.job_id = job_id
        self.temp_dir: Optional[Path] = None
        self.compose_file: Optional[Path] = None
        self.project_name = f"lab-backup-verify-{job_id}"

        # PostgreSQL settings for test pod
        self.test_db_user = "testuser"
        self.test_db_password = self._generate_password()
        self.test_db_name = "test_restore"

    def _generate_password(self) -> str:
        """Generate a random password for the test database."""
        import secrets
        return secrets.token_urlsafe(32)

    async def verify_backup(
        self,
        backup_file: Path,
        encrypted: bool = False
    ) -> Dict[str, Any]:
        """
        Verify a backup by restoring it to an isolated test pod.

        Args:
            backup_file: Path to backup file (must be accessible)
            encrypted: Whether the backup is encrypted

        Returns:
            Dictionary with verification results:
            {
                'success': bool,
                'table_count': int,
                'size_bytes': int,
                'duration_seconds': int,
                'error': Optional[str]
            }
        """
        start_time = time.time()

        try:
            # Create temporary directory for this verification
            self.temp_dir = Path(tempfile.mkdtemp(prefix=f"verify-{self.job_id}-"))
            logger.info(f"Created temp directory: {self.temp_dir}")

            # Decrypt backup if needed
            file_to_restore = backup_file
            if encrypted:
                logger.info("Decrypting backup...")
                file_to_restore = await self._decrypt_backup(backup_file)

            # Create docker-compose configuration
            logger.info("Creating test pod configuration...")
            self._create_compose_file(file_to_restore)

            # Start test pod
            logger.info("Starting test pod...")
            await self._start_test_pod()

            # Wait for database to be ready
            logger.info("Waiting for database to be ready...")
            await self._wait_for_database()

            # Restore backup
            logger.info("Restoring backup to test database...")
            await self._restore_backup(file_to_restore)

            # Verify restoration
            logger.info("Verifying restoration...")
            table_count, size_bytes = await self._verify_restoration()

            duration = int(time.time() - start_time)

            logger.info(f"Verification successful: {table_count} tables, {size_bytes} bytes, {duration}s")

            return {
                'success': True,
                'table_count': table_count,
                'size_bytes': size_bytes,
                'duration_seconds': duration,
                'error': None
            }

        except Exception as e:
            duration = int(time.time() - start_time)
            logger.error(f"Verification failed: {e}", exc_info=True)

            return {
                'success': False,
                'table_count': None,
                'size_bytes': None,
                'duration_seconds': duration,
                'error': str(e)
            }

        finally:
            # Always cleanup test pod
            await self._cleanup()

    async def _decrypt_backup(self, backup_file: Path) -> Path:
        """
        Decrypt an encrypted backup file.

        Args:
            backup_file: Path to encrypted backup

        Returns:
            Path to decrypted backup file
        """
        if not settings.ENCRYPTION_KEY:
            raise RecoveryTestError("Backup is encrypted but ENCRYPTION_KEY not available")

        decrypted_file = self.temp_dir / backup_file.name.replace('.encrypted', '')

        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: decrypt_backup(
                backup_file,
                decrypted_file,
                settings.ENCRYPTION_KEY,
                use_chunked=False
            )
        )

        logger.info(f"Backup decrypted to: {decrypted_file}")
        return decrypted_file

    def _create_compose_file(self, backup_file: Path):
        """
        Create docker-compose.yml file for test pod.

        Args:
            backup_file: Path to backup file to mount in container
        """
        # Load template
        template_path = Path(__file__).parent / "test-pod-template.yml"

        if not template_path.exists():
            raise RecoveryTestError(f"Test pod template not found: {template_path}")

        template = template_path.read_text()

        # Substitute environment variables
        compose_content = template.replace('${JOB_ID}', str(self.job_id))
        compose_content = compose_content.replace('${POSTGRES_USER}', self.test_db_user)
        compose_content = compose_content.replace('${POSTGRES_PASSWORD}', self.test_db_password)
        compose_content = compose_content.replace('${POSTGRES_DB}', self.test_db_name)
        compose_content = compose_content.replace('${BACKUP_FILE_PATH}', str(backup_file.absolute()))

        # Write to temp directory
        self.compose_file = self.temp_dir / "docker-compose.yml"
        self.compose_file.write_text(compose_content)

        logger.info(f"Created compose file: {self.compose_file}")

    async def _start_test_pod(self):
        """Start the test pod using docker-compose."""
        cmd = [
            "docker-compose",
            "-f", str(self.compose_file),
            "-p", self.project_name,
            "up", "-d"
        ]

        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await result.wait()

        if result.returncode != 0:
            raise RecoveryTestError(f"Failed to start test pod: {stderr.decode()}")

        logger.info("Test pod started successfully")

    async def _wait_for_database(self, timeout: int = 60):
        """
        Wait for test database to be ready.

        Args:
            timeout: Maximum time to wait in seconds
        """
        start_time = time.time()
        container_name = f"lab-backup-verify-{self.job_id}"

        while time.time() - start_time < timeout:
            cmd = [
                "docker", "exec",
                container_name,
                "pg_isready",
                "-U", self.test_db_user,
                "-d", self.test_db_name
            ]

            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await result.wait()

            if result.returncode == 0:
                logger.info("Test database is ready")
                return

            await asyncio.sleep(2)

        raise RecoveryTestError(f"Test database not ready after {timeout}s")

    async def _restore_backup(self, backup_file: Path):
        """
        Restore backup to test database.

        Args:
            backup_file: Path to backup file (already mounted in container at /backup/restore.sql.gz)
        """
        container_name = f"lab-backup-verify-{self.job_id}"

        # Run pg_restore inside the container
        cmd = [
            "docker", "exec",
            container_name,
            "pg_restore",
            "-U", self.test_db_user,
            "-d", self.test_db_name,
            "-v",
            "/backup/restore.sql.gz"
        ]

        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await result.wait()

        # pg_restore returns non-zero for warnings, check stderr for actual errors
        stderr_text = stderr.decode() if stderr else ""

        if "error" in stderr_text.lower() and result.returncode != 0:
            raise RecoveryTestError(f"Restore failed: {stderr_text}")

        logger.info("Backup restored successfully")

    async def _verify_restoration(self) -> Tuple[int, int]:
        """
        Verify the restored database by running verification queries.

        Returns:
            Tuple of (table_count, size_bytes)
        """
        container_name = f"lab-backup-verify-{self.job_id}"

        # Count tables
        table_count_cmd = [
            "docker", "exec",
            container_name,
            "psql",
            "-U", self.test_db_user,
            "-d", self.test_db_name,
            "-t",  # Tuples only (no headers)
            "-c", "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
        ]

        result = await asyncio.create_subprocess_exec(
            *table_count_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await result.wait()

        if result.returncode != 0:
            raise RecoveryTestError(f"Failed to count tables: {stderr.decode()}")

        table_count = int(stdout.decode().strip())

        # Get database size
        size_cmd = [
            "docker", "exec",
            container_name,
            "psql",
            "-U", self.test_db_user,
            "-d", self.test_db_name,
            "-t",
            "-c", f"SELECT pg_database_size('{self.test_db_name}');"
        ]

        result = await asyncio.create_subprocess_exec(
            *size_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await result.wait()

        if result.returncode != 0:
            raise RecoveryTestError(f"Failed to get database size: {stderr.decode()}")

        size_bytes = int(stdout.decode().strip())

        # Basic sanity checks
        if table_count == 0:
            raise RecoveryTestError("No tables found in restored database")

        if size_bytes < 1000:  # Less than 1KB is suspicious
            raise RecoveryTestError(f"Database size suspiciously small: {size_bytes} bytes")

        return table_count, size_bytes

    async def _cleanup(self):
        """Clean up test pod and temporary files."""
        logger.info("Cleaning up test pod...")

        try:
            # Stop and remove test pod
            if self.compose_file and self.compose_file.exists():
                cmd = [
                    "docker-compose",
                    "-f", str(self.compose_file),
                    "-p", self.project_name,
                    "down", "-v"  # Remove volumes
                ]

                result = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                await result.wait()

                logger.info("Test pod removed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

        finally:
            # Remove temporary directory
            if self.temp_dir and self.temp_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(self.temp_dir)
                    logger.info(f"Removed temp directory: {self.temp_dir}")
                except Exception as e:
                    logger.error(f"Failed to remove temp directory: {e}")
