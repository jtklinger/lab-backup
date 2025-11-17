"""
Encryption utilities for backup data.

Uses Fernet (symmetric encryption) from cryptography library.
Data is encrypted before being written to storage and decrypted when retrieved.
"""
import base64
from pathlib import Path
from typing import BinaryIO, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import logging

logger = logging.getLogger(__name__)


class BackupEncryption:
    """Handle encryption and decryption of backup data."""

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption with a key.

        Args:
            encryption_key: Base64-encoded Fernet key. If None, generates a new one.
        """
        if encryption_key:
            self.key = encryption_key.encode()
            self.fernet = Fernet(self.key)
        else:
            # Generate a new key
            self.key = Fernet.generate_key()
            self.fernet = Fernet(self.key)

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new encryption key.

        Returns:
            Base64-encoded Fernet key as string
        """
        key = Fernet.generate_key()
        return key.decode('utf-8')

    @staticmethod
    def derive_key_from_password(password: str, salt: bytes = None) -> tuple[str, bytes]:
        """
        Derive an encryption key from a password.

        Args:
            password: Password to derive key from
            salt: Salt for key derivation. If None, generates random salt.

        Returns:
            Tuple of (base64-encoded key, salt used)
        """
        if salt is None:
            import os
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key.decode('utf-8'), salt

    def encrypt_file(self, input_path: Path, output_path: Path) -> dict:
        """
        Encrypt a file.

        Args:
            input_path: Path to file to encrypt
            output_path: Path to write encrypted file

        Returns:
            Dictionary with encryption metadata
        """
        try:
            # Read input file
            with open(input_path, 'rb') as f:
                data = f.read()

            original_size = len(data)

            # Encrypt
            encrypted_data = self.fernet.encrypt(data)

            # Write encrypted file
            with open(output_path, 'wb') as f:
                f.write(encrypted_data)

            encrypted_size = len(encrypted_data)

            logger.info(
                f"Encrypted {input_path.name}: "
                f"{original_size} -> {encrypted_size} bytes "
                f"({encrypted_size/original_size*100:.1f}%)"
            )

            return {
                "original_size": original_size,
                "encrypted_size": encrypted_size,
                "encrypted": True
            }

        except Exception as e:
            logger.error(f"Failed to encrypt file {input_path}: {e}")
            raise

    def decrypt_file(self, input_path: Path, output_path: Path) -> dict:
        """
        Decrypt a file.

        Args:
            input_path: Path to encrypted file
            output_path: Path to write decrypted file

        Returns:
            Dictionary with decryption metadata
        """
        try:
            # Read encrypted file
            with open(input_path, 'rb') as f:
                encrypted_data = f.read()

            encrypted_size = len(encrypted_data)

            # Decrypt
            decrypted_data = self.fernet.decrypt(encrypted_data)

            # Write decrypted file
            with open(output_path, 'wb') as f:
                f.write(decrypted_data)

            decrypted_size = len(decrypted_data)

            logger.info(
                f"Decrypted {input_path.name}: "
                f"{encrypted_size} -> {decrypted_size} bytes"
            )

            return {
                "encrypted_size": encrypted_size,
                "decrypted_size": decrypted_size,
                "decrypted": True
            }

        except Exception as e:
            logger.error(f"Failed to decrypt file {input_path}: {e}")
            raise

    def encrypt_stream(self, data: bytes) -> bytes:
        """
        Encrypt raw bytes.

        Args:
            data: Data to encrypt

        Returns:
            Encrypted data
        """
        return self.fernet.encrypt(data)

    def decrypt_stream(self, encrypted_data: bytes) -> bytes:
        """
        Decrypt raw bytes.

        Args:
            encrypted_data: Encrypted data

        Returns:
            Decrypted data
        """
        return self.fernet.decrypt(encrypted_data)

    def encrypt_file_chunked(
        self,
        input_path: Path,
        output_path: Path,
        chunk_size: int = 64 * 1024 * 1024  # 64MB chunks
    ) -> dict:
        """
        Encrypt a large file in chunks to save memory.

        Note: This encrypts each chunk separately, which is less secure
        than encrypting the whole file. Use for very large files only.

        Args:
            input_path: Path to file to encrypt
            output_path: Path to write encrypted file
            chunk_size: Size of chunks to process

        Returns:
            Dictionary with encryption metadata
        """
        try:
            original_size = 0
            encrypted_size = 0

            with open(input_path, 'rb') as f_in:
                with open(output_path, 'wb') as f_out:
                    while chunk := f_in.read(chunk_size):
                        original_size += len(chunk)
                        encrypted_chunk = self.fernet.encrypt(chunk)
                        encrypted_size += len(encrypted_chunk)

                        # Write chunk size first (for decryption)
                        chunk_size_bytes = len(encrypted_chunk).to_bytes(8, 'big')
                        f_out.write(chunk_size_bytes)
                        f_out.write(encrypted_chunk)

            logger.info(
                f"Encrypted (chunked) {input_path.name}: "
                f"{original_size} -> {encrypted_size} bytes"
            )

            return {
                "original_size": original_size,
                "encrypted_size": encrypted_size,
                "encrypted": True,
                "chunked": True
            }

        except Exception as e:
            logger.error(f"Failed to encrypt file (chunked) {input_path}: {e}")
            raise

    def decrypt_file_chunked(self, input_path: Path, output_path: Path) -> dict:
        """
        Decrypt a file that was encrypted in chunks.

        Args:
            input_path: Path to encrypted file
            output_path: Path to write decrypted file

        Returns:
            Dictionary with decryption metadata
        """
        try:
            encrypted_size = 0
            decrypted_size = 0

            with open(input_path, 'rb') as f_in:
                with open(output_path, 'wb') as f_out:
                    while True:
                        # Read chunk size
                        chunk_size_bytes = f_in.read(8)
                        if not chunk_size_bytes:
                            break

                        chunk_size = int.from_bytes(chunk_size_bytes, 'big')
                        encrypted_size += chunk_size

                        # Read encrypted chunk
                        encrypted_chunk = f_in.read(chunk_size)
                        if not encrypted_chunk:
                            break

                        # Decrypt and write
                        decrypted_chunk = self.fernet.decrypt(encrypted_chunk)
                        decrypted_size += len(decrypted_chunk)
                        f_out.write(decrypted_chunk)

            logger.info(
                f"Decrypted (chunked) {input_path.name}: "
                f"{encrypted_size} -> {decrypted_size} bytes"
            )

            return {
                "encrypted_size": encrypted_size,
                "decrypted_size": decrypted_size,
                "decrypted": True,
                "chunked": True
            }

        except Exception as e:
            logger.error(f"Failed to decrypt file (chunked) {input_path}: {e}")
            raise

    def get_key_string(self) -> str:
        """Get the encryption key as a string for storage."""
        return self.key.decode('utf-8')


# Utility functions

def generate_encryption_key() -> str:
    """Generate a new encryption key."""
    return BackupEncryption.generate_key()


def encrypt_backup(
    input_path: Path,
    output_path: Path,
    encryption_key: str,
    use_chunked: bool = False
) -> dict:
    """
    Encrypt a backup file.

    Args:
        input_path: Path to backup file
        output_path: Path for encrypted output
        encryption_key: Encryption key
        use_chunked: Use chunked encryption for large files

    Returns:
        Dictionary with encryption metadata
    """
    encryptor = BackupEncryption(encryption_key)

    if use_chunked:
        return encryptor.encrypt_file_chunked(input_path, output_path)
    else:
        return encryptor.encrypt_file(input_path, output_path)


def decrypt_backup(
    input_path: Path,
    output_path: Path,
    encryption_key: str,
    use_chunked: bool = False
) -> dict:
    """
    Decrypt a backup file.

    Args:
        input_path: Path to encrypted backup
        output_path: Path for decrypted output
        encryption_key: Encryption key
        use_chunked: Use chunked decryption

    Returns:
        Dictionary with decryption metadata
    """
    decryptor = BackupEncryption(encryption_key)

    if use_chunked:
        return decryptor.decrypt_file_chunked(input_path, output_path)
    else:
        return decryptor.decrypt_file(input_path, output_path)


# SSH Key Encryption Utilities

class SSHKeyEncryption:
    """Handle encryption and decryption of SSH private keys."""

    def __init__(self, secret_key: str):
        """
        Initialize SSH key encryption with application secret key.

        Args:
            secret_key: Application SECRET_KEY from environment
        """
        # Derive a Fernet key from the secret key using PBKDF2
        # Use a fixed salt since we're deriving from the app secret
        salt = b'ssh_key_encryption_salt_v1'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        fernet_key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
        self.fernet = Fernet(fernet_key)

    def encrypt_private_key(self, private_key: str) -> str:
        """
        Encrypt an SSH private key.

        Args:
            private_key: SSH private key in PEM format

        Returns:
            Encrypted private key as base64 string
        """
        try:
            encrypted_bytes = self.fernet.encrypt(private_key.encode('utf-8'))
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encrypt SSH private key: {e}")
            raise

    def decrypt_private_key(self, encrypted_key: str) -> str:
        """
        Decrypt an SSH private key.

        Args:
            encrypted_key: Encrypted private key as base64 string

        Returns:
            Decrypted SSH private key in PEM format
        """
        try:
            encrypted_bytes = base64.b64decode(encrypted_key.encode('utf-8'))
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to decrypt SSH private key: {e}")
            raise


def encrypt_ssh_private_key(private_key: str, secret_key: str) -> str:
    """
    Encrypt an SSH private key using the application secret.

    Args:
        private_key: SSH private key in PEM format
        secret_key: Application SECRET_KEY

    Returns:
        Encrypted private key as base64 string
    """
    encryptor = SSHKeyEncryption(secret_key)
    return encryptor.encrypt_private_key(private_key)


def decrypt_ssh_private_key(encrypted_key: str, secret_key: str) -> str:
    """
    Decrypt an SSH private key using the application secret.

    Args:
        encrypted_key: Encrypted private key as base64 string
        secret_key: Application SECRET_KEY

    Returns:
        Decrypted SSH private key in PEM format
    """
    decryptor = SSHKeyEncryption(secret_key)
    return decryptor.decrypt_private_key(encrypted_key)


# Password Encryption Utilities (reuse SSH key encryption)

def encrypt_password(password: str, secret_key: str) -> str:
    """
    Encrypt a password using the application secret.

    Uses the same encryption method as SSH keys for consistency.

    Args:
        password: Plain text password
        secret_key: Application SECRET_KEY

    Returns:
        Encrypted password as base64 string
    """
    encryptor = SSHKeyEncryption(secret_key)
    return encryptor.encrypt_private_key(password)


def decrypt_password(encrypted_password: str, secret_key: str) -> str:
    """
    Decrypt a password using the application secret.

    Args:
        encrypted_password: Encrypted password as base64 string
        secret_key: Application SECRET_KEY

    Returns:
        Decrypted plain text password
    """
    decryptor = SSHKeyEncryption(secret_key)
    return decryptor.decrypt_private_key(encrypted_password)
