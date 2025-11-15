"""
SSH key manager for KVM host connections.

Handles retrieval and temporary deployment of SSH keys stored in the database.
"""
import os
import tempfile
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.infrastructure import SSHKey
from backend.core.encryption import decrypt_ssh_private_key
from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class SSHKeyManager:
    """Manage SSH keys for KVM host authentication."""

    def __init__(self, db: AsyncSession):
        """
        Initialize SSH key manager.

        Args:
            db: Database session for retrieving SSH keys
        """
        self.db = db
        self.settings = get_settings()

    async def get_ssh_key(self, kvm_host_id: int) -> Optional[SSHKey]:
        """
        Get the SSH key for a KVM host from the database.

        Args:
            kvm_host_id: ID of the KVM host

        Returns:
            SSHKey model if found, None otherwise
        """
        stmt = select(SSHKey).where(SSHKey.kvm_host_id == kvm_host_id).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def decrypt_key(self, ssh_key: SSHKey) -> str:
        """
        Decrypt an SSH private key.

        Args:
            ssh_key: SSHKey model with encrypted private key

        Returns:
            Decrypted private key as string
        """
        try:
            return decrypt_ssh_private_key(
                ssh_key.private_key_encrypted,
                self.settings.SECRET_KEY
            )
        except Exception as e:
            logger.error(f"Failed to decrypt SSH key (ID: {ssh_key.id}): {e}")
            raise

    @asynccontextmanager
    async def use_ssh_key(self, kvm_host_id: int):
        """
        Context manager for using an SSH key from the database.

        This will:
        1. Check if there's an SSH key in the database for the host
        2. If yes, decrypt it and write to a temporary file
        3. Yield the path to the temporary key file (or None if no database key)
        4. Clean up the temporary file when done

        Args:
            kvm_host_id: ID of the KVM host

        Yields:
            Path to temporary SSH key file, or None if using default keys
        """
        ssh_key = await self.get_ssh_key(kvm_host_id)

        if not ssh_key:
            # No database key, use default SSH keys from ~/.ssh
            logger.debug(f"No database SSH key for KVM host {kvm_host_id}, using default keys")
            yield None
            return

        # Create temporary file for the SSH key
        temp_key_file = None
        try:
            # Decrypt the private key
            private_key = await self.decrypt_key(ssh_key)

            # Write to temporary file with restricted permissions
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem') as f:
                temp_key_file = f.name
                f.write(private_key)

            # Set proper permissions (read-only for owner)
            os.chmod(temp_key_file, 0o600)

            logger.info(f"Using database SSH key (ID: {ssh_key.id}) for KVM host {kvm_host_id}")

            # Update last_used timestamp
            from datetime import datetime
            ssh_key.last_used = datetime.utcnow()
            await self.db.commit()

            yield temp_key_file

        except Exception as e:
            logger.error(f"Failed to prepare SSH key for KVM host {kvm_host_id}: {e}")
            raise

        finally:
            # Clean up temporary key file
            if temp_key_file and os.path.exists(temp_key_file):
                try:
                    os.unlink(temp_key_file)
                    logger.debug(f"Cleaned up temporary SSH key file: {temp_key_file}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary SSH key file {temp_key_file}: {e}")


async def get_ssh_config_for_host(
    db: AsyncSession,
    kvm_host_id: int,
    hostname: str
) -> Optional[str]:
    """
    Generate SSH config entry for a KVM host with database-stored key.

    Args:
        db: Database session
        kvm_host_id: ID of the KVM host
        hostname: Hostname or IP of the KVM host

    Returns:
        SSH config entry as string, or None if no database key
    """
    manager = SSHKeyManager(db)
    ssh_key = await manager.get_ssh_key(kvm_host_id)

    if not ssh_key:
        return None

    # Note: This returns a config template, actual key file path
    # would need to be filled in when using the key
    return f"""
Host {hostname}
    IdentityFile {{key_file_path}}
    StrictHostKeyChecking accept-new
    UserKnownHostsFile ~/.ssh/known_hosts
    ServerAliveInterval 60
    ServerAliveCountMax 3
    ConnectTimeout 30
"""
