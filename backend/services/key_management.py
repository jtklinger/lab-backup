"""
Encryption Key Management Service

Manages encryption keys stored in the database using envelope encryption:
- Master KEK (Key Encryption Key) from .env encrypts all DEKs
- DEKs (Data Encryption Keys) stored encrypted in database
- Supports key rotation, versioning, and export/import
"""

import logging
from datetime import datetime
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.models.encryption import EncryptionKey, EncryptionKeyType

logger = logging.getLogger(__name__)


class KeyManagementError(Exception):
    """Exception raised for key management errors."""
    pass


class KeyManagementService:
    """
    Service for managing encryption keys using envelope encryption.

    Architecture:
    - Master KEK from ENCRYPTION_KEY in .env encrypts all DEKs
    - DEKs stored encrypted in database for portability
    - Supports GLOBAL, STORAGE_BACKEND, VM, and CONTAINER keys
    - Key versioning and rotation support
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize key management service.

        Args:
            db: Async database session
        """
        self.db = db
        self.master_kek = self._get_master_kek()

    def _get_master_kek(self) -> bytes:
        """
        Get the master KEK from environment.

        Returns:
            Master KEK as bytes

        Raises:
            KeyManagementError: If ENCRYPTION_KEY not configured
        """
        if not settings.ENCRYPTION_KEY:
            raise KeyManagementError(
                "ENCRYPTION_KEY not configured in .env. "
                "This key encrypts all database-stored keys."
            )

        # ENCRYPTION_KEY should be base64-encoded Fernet key
        return settings.ENCRYPTION_KEY.encode('utf-8')

    async def generate_key(
        self,
        key_type: EncryptionKeyType,
        reference_id: Optional[int] = None,
        algorithm: str = "Fernet"
    ) -> EncryptionKey:
        """
        Generate a new encryption key.

        Args:
            key_type: Type of key (GLOBAL, STORAGE_BACKEND, VM, CONTAINER)
            reference_id: ID of related entity (None for GLOBAL)
            algorithm: Encryption algorithm (default: Fernet)

        Returns:
            New EncryptionKey instance (not yet committed)

        Raises:
            KeyManagementError: If key generation fails
        """
        try:
            # Generate new DEK
            dek = Fernet.generate_key()

            # Encrypt DEK with master KEK
            encrypted_dek = self._encrypt_key(dek)

            # Create encryption key record
            encryption_key = EncryptionKey(
                key_type=key_type,
                reference_id=reference_id,
                encrypted_key=encrypted_dek,
                key_version=1,
                algorithm=algorithm,
                active=True,
                created_at=datetime.utcnow(),
                key_metadata={
                    "generated_by": "KeyManagementService",
                    "algorithm": algorithm
                }
            )

            self.db.add(encryption_key)
            await self.db.flush()  # Get the ID without committing

            logger.info(
                f"Generated new {key_type.value} encryption key "
                f"(ID: {encryption_key.id}, ref: {reference_id})"
            )

            return encryption_key

        except Exception as e:
            logger.error(f"Failed to generate encryption key: {e}", exc_info=True)
            raise KeyManagementError(f"Key generation failed: {e}")

    def _encrypt_key(self, dek: bytes) -> bytes:
        """
        Encrypt a DEK using the master KEK.

        Args:
            dek: Data Encryption Key to encrypt

        Returns:
            Encrypted DEK
        """
        fernet = Fernet(self.master_kek)
        return fernet.encrypt(dek)

    def _decrypt_key(self, encrypted_dek: bytes) -> bytes:
        """
        Decrypt a DEK using the master KEK.

        Args:
            encrypted_dek: Encrypted Data Encryption Key

        Returns:
            Decrypted DEK

        Raises:
            KeyManagementError: If decryption fails
        """
        try:
            fernet = Fernet(self.master_kek)
            return fernet.decrypt(encrypted_dek)
        except Exception as e:
            logger.error(f"Failed to decrypt key: {e}", exc_info=True)
            raise KeyManagementError(
                "Failed to decrypt key. Master KEK may have changed or key is corrupted."
            )

    async def get_active_key(
        self,
        key_type: EncryptionKeyType,
        reference_id: Optional[int] = None,
        create_if_missing: bool = False
    ) -> Optional[EncryptionKey]:
        """
        Get the active encryption key for a given type and reference.

        Args:
            key_type: Type of key to retrieve
            reference_id: Reference ID (None for GLOBAL)
            create_if_missing: If True, create key if it doesn't exist

        Returns:
            Active EncryptionKey or None if not found

        Raises:
            KeyManagementError: If multiple active keys found
        """
        stmt = select(EncryptionKey).where(
            and_(
                EncryptionKey.key_type == key_type,
                EncryptionKey.reference_id == reference_id,
                EncryptionKey.active == True
            )
        ).order_by(EncryptionKey.key_version.desc())

        result = await self.db.execute(stmt)
        keys = result.scalars().all()

        if len(keys) > 1:
            logger.error(
                f"Multiple active keys found for {key_type.value} "
                f"(ref: {reference_id}): {[k.id for k in keys]}"
            )
            raise KeyManagementError(
                f"Data integrity error: Multiple active keys for {key_type.value}"
            )

        if len(keys) == 1:
            return keys[0]

        # No active key found
        if create_if_missing:
            logger.info(
                f"No active {key_type.value} key found (ref: {reference_id}), "
                "creating new key"
            )
            key = await self.generate_key(key_type, reference_id)
            await self.db.commit()
            return key

        return None

    async def get_decrypted_key(
        self,
        key_type: EncryptionKeyType,
        reference_id: Optional[int] = None,
        create_if_missing: bool = False
    ) -> Optional[bytes]:
        """
        Get the decrypted DEK for a given type and reference.

        Args:
            key_type: Type of key to retrieve
            reference_id: Reference ID (None for GLOBAL)
            create_if_missing: If True, create key if it doesn't exist

        Returns:
            Decrypted DEK as bytes, or None if not found

        Raises:
            KeyManagementError: If decryption fails
        """
        encryption_key = await self.get_active_key(
            key_type, reference_id, create_if_missing
        )

        if not encryption_key:
            return None

        return self._decrypt_key(encryption_key.encrypted_key)

    async def rotate_key(
        self,
        key_type: EncryptionKeyType,
        reference_id: Optional[int] = None
    ) -> Tuple[EncryptionKey, EncryptionKey]:
        """
        Rotate an encryption key by creating a new version.

        Args:
            key_type: Type of key to rotate
            reference_id: Reference ID (None for GLOBAL)

        Returns:
            Tuple of (old_key, new_key)

        Raises:
            KeyManagementError: If rotation fails
        """
        # Get current active key
        old_key = await self.get_active_key(key_type, reference_id)

        if not old_key:
            raise KeyManagementError(
                f"No active {key_type.value} key found to rotate "
                f"(ref: {reference_id})"
            )

        # Mark old key as inactive
        old_key.active = False
        old_key.rotated_at = datetime.utcnow()

        # Generate new key with incremented version
        new_dek = Fernet.generate_key()
        encrypted_dek = self._encrypt_key(new_dek)

        new_key = EncryptionKey(
            key_type=key_type,
            reference_id=reference_id,
            encrypted_key=encrypted_dek,
            key_version=old_key.key_version + 1,
            algorithm=old_key.algorithm,
            active=True,
            created_at=datetime.utcnow(),
            key_metadata={
                "generated_by": "KeyManagementService",
                "rotated_from_key_id": old_key.id,
                "rotated_from_version": old_key.key_version
            }
        )

        self.db.add(new_key)
        await self.db.commit()
        await self.db.refresh(new_key)

        logger.info(
            f"Rotated {key_type.value} key (ref: {reference_id}): "
            f"v{old_key.key_version} (ID {old_key.id}) -> "
            f"v{new_key.key_version} (ID {new_key.id})"
        )

        return old_key, new_key

    async def get_key_by_id(self, key_id: int) -> Optional[EncryptionKey]:
        """
        Get encryption key by ID.

        Args:
            key_id: ID of encryption key

        Returns:
            EncryptionKey or None if not found
        """
        return await self.db.get(EncryptionKey, key_id)

    async def get_decrypted_key_by_id(self, key_id: int) -> Optional[bytes]:
        """
        Get decrypted DEK by key ID.

        Args:
            key_id: ID of encryption key

        Returns:
            Decrypted DEK or None if not found

        Raises:
            KeyManagementError: If decryption fails
        """
        encryption_key = await self.get_key_by_id(key_id)

        if not encryption_key:
            return None

        return self._decrypt_key(encryption_key.encrypted_key)

    async def list_all_keys(self) -> list[EncryptionKey]:
        """
        List all encryption keys in the database.

        Returns:
            List of all EncryptionKey instances
        """
        stmt = select(EncryptionKey).order_by(
            EncryptionKey.key_type,
            EncryptionKey.reference_id,
            EncryptionKey.key_version.desc()
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def export_keys_for_disaster_recovery(self) -> list[dict]:
        """
        Export all encryption keys for disaster recovery.

        Returns decrypted keys - this should only be used for export
        to encrypted bundles with user-provided passphrase.

        Returns:
            List of dictionaries containing key data

        Security Warning:
            This method returns DECRYPTED keys. The caller MUST
            immediately encrypt this data with a strong passphrase.
        """
        all_keys = await self.list_all_keys()

        exported_keys = []
        for key in all_keys:
            decrypted_dek = self._decrypt_key(key.encrypted_key)

            exported_keys.append({
                "id": key.id,
                "key_type": key.key_type.value,
                "reference_id": key.reference_id,
                "key_version": key.key_version,
                "algorithm": key.algorithm,
                "active": key.active,
                "created_at": key.created_at.isoformat(),
                "rotated_at": key.rotated_at.isoformat() if key.rotated_at else None,
                "decrypted_key": decrypted_dek.decode('utf-8'),  # Base64-encoded Fernet key
                "metadata": key.key_metadata
            })

        logger.warning(
            f"Exported {len(exported_keys)} decrypted encryption keys for disaster recovery. "
            "IMMEDIATELY encrypt this data with a strong passphrase!"
        )

        return exported_keys

    async def import_keys_from_backup(
        self,
        keys_data: list[dict],
        reencrypt_with_current_kek: bool = True
    ) -> int:
        """
        Import encryption keys from a disaster recovery backup.

        Args:
            keys_data: List of key dictionaries (from export_keys_for_disaster_recovery)
            reencrypt_with_current_kek: If True, re-encrypt keys with current master KEK

        Returns:
            Number of keys imported

        Raises:
            KeyManagementError: If import fails
        """
        imported_count = 0

        for key_data in keys_data:
            try:
                # Get the decrypted DEK from export
                dek = key_data['decrypted_key'].encode('utf-8')

                # Re-encrypt with current master KEK if requested
                if reencrypt_with_current_kek:
                    encrypted_dek = self._encrypt_key(dek)
                else:
                    # Use as-is (assumes same master KEK)
                    encrypted_dek = dek

                # Create new encryption key record
                key = EncryptionKey(
                    key_type=EncryptionKeyType(key_data['key_type']),
                    reference_id=key_data['reference_id'],
                    encrypted_key=encrypted_dek,
                    key_version=key_data['key_version'],
                    algorithm=key_data['algorithm'],
                    active=key_data['active'],
                    created_at=datetime.fromisoformat(key_data['created_at']),
                    rotated_at=datetime.fromisoformat(key_data['rotated_at']) if key_data['rotated_at'] else None,
                    key_metadata=key_data.get('metadata', {})
                )

                self.db.add(key)
                imported_count += 1

            except Exception as e:
                logger.error(f"Failed to import key {key_data.get('id')}: {e}")
                raise KeyManagementError(f"Key import failed: {e}")

        await self.db.commit()

        logger.info(f"Successfully imported {imported_count} encryption keys")

        return imported_count
