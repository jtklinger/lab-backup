#!/usr/bin/env python3
"""
Encryption Key Export Tool

Exports all encryption keys from the database to an encrypted bundle file.
This is critical for disaster recovery scenarios where the database backup
alone is not sufficient to decrypt backups.

Usage:
    python scripts/export-keys.py --output keys-backup.encrypted
    python scripts/export-keys.py --output keys-backup.encrypted --passphrase-file /secure/passphrase.txt

Security:
    - Keys are exported DECRYPTED and then re-encrypted with user passphrase
    - Bundle uses Fernet encryption (AES-128-CBC)
    - Passphrase should be at least 16 characters
    - Store bundle and passphrase separately and securely
"""

import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path
from datetime import datetime
from cryptography.fernet import Fernet
import hashlib

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.base import AsyncSessionLocal
from backend.services.key_management import KeyManagementService


def derive_key_from_passphrase(passphrase: str) -> bytes:
    """
    Derive a Fernet key from a user passphrase using PBKDF2.

    Args:
        passphrase: User-provided passphrase

    Returns:
        32-byte Fernet-compatible key (base64-encoded)
    """
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    # Use a fixed salt (not ideal but necessary for import)
    # In production, salt should be stored with the bundle
    salt = b"lab-backup-key-export-v1"

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )

    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode('utf-8')))
    return key


def encrypt_bundle(data: dict, passphrase: str) -> bytes:
    """
    Encrypt key bundle with user passphrase.

    Args:
        data: Dictionary containing keys and metadata
        passphrase: User-provided passphrase

    Returns:
        Encrypted bundle as bytes
    """
    # Serialize data to JSON
    json_data = json.dumps(data, indent=2, default=str)

    # Derive encryption key from passphrase
    encryption_key = derive_key_from_passphrase(passphrase)

    # Encrypt with Fernet
    fernet = Fernet(encryption_key)
    encrypted = fernet.encrypt(json_data.encode('utf-8'))

    return encrypted


async def export_keys(output_path: Path, passphrase: str):
    """
    Export all encryption keys to encrypted bundle.

    Args:
        output_path: Path to write encrypted bundle
        passphrase: Passphrase to encrypt bundle
    """
    print("=" * 70)
    print("ENCRYPTION KEY EXPORT TOOL")
    print("=" * 70)
    print()

    async with AsyncSessionLocal() as db:
        try:
            # Initialize key management service
            print("Connecting to database...")
            key_service = KeyManagementService(db)

            # Export all keys (DECRYPTED - this is sensitive!)
            print("Exporting encryption keys from database...")
            print()
            print("⚠️  WARNING: Exporting DECRYPTED encryption keys!")
            print("    These keys will be re-encrypted with your passphrase.")
            print()

            keys_data = await key_service.export_keys_for_disaster_recovery()

            if not keys_data:
                print("✗ No encryption keys found in database.")
                print("  This may indicate the system is using .env-only encryption.")
                return

            # Create export bundle with metadata
            bundle = {
                "version": 1,
                "export_date": datetime.utcnow().isoformat(),
                "key_count": len(keys_data),
                "keys": keys_data,
                "metadata": {
                    "tool": "export-keys.py",
                    "format": "encrypted_json",
                    "encryption": "fernet_pbkdf2"
                }
            }

            # Encrypt bundle with user passphrase
            print(f"Encrypting {len(keys_data)} keys with passphrase...")
            encrypted_bundle = encrypt_bundle(bundle, passphrase)

            # Write to file
            output_path.write_bytes(encrypted_bundle)

            # Calculate checksum for verification
            checksum = hashlib.sha256(encrypted_bundle).hexdigest()

            print()
            print("=" * 70)
            print("✓ EXPORT SUCCESSFUL")
            print("=" * 70)
            print()
            print(f"Export Summary:")
            print(f"  Keys Exported:  {len(keys_data)}")
            print(f"  Output File:    {output_path}")
            print(f"  File Size:      {len(encrypted_bundle)} bytes")
            print(f"  SHA256:         {checksum}")
            print()
            print("Key Breakdown:")
            key_types = {}
            for key in keys_data:
                key_type = key['key_type']
                key_types[key_type] = key_types.get(key_type, 0) + 1

            for key_type, count in sorted(key_types.items()):
                active_count = sum(1 for k in keys_data if k['key_type'] == key_type and k['active'])
                print(f"  {key_type.upper()}: {count} total ({active_count} active)")

            print()
            print("⚠️  IMPORTANT SECURITY INSTRUCTIONS:")
            print()
            print("1. Store this encrypted bundle in a secure location")
            print("   (e.g., password manager, encrypted USB, secure vault)")
            print()
            print("2. Store the passphrase SEPARATELY from the bundle")
            print("   (e.g., different password manager, printed and locked away)")
            print()
            print("3. Test the import process to ensure recoverability:")
            print(f"   python scripts/import-keys.py --input {output_path} --verify-only")
            print()
            print("4. Keep this bundle updated when keys are rotated:")
            print("   Re-run this export after any key rotation")
            print()
            print("5. This bundle contains ALL keys needed to decrypt backups")
            print("   If both bundle AND passphrase are lost, backups are UNRECOVERABLE")
            print()

        except Exception as e:
            print(f"\n✗ ERROR: Export failed: {e}", file=sys.stderr)
            sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(
        description="Export encryption keys to encrypted bundle for disaster recovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write encrypted key bundle"
    )
    parser.add_argument(
        "--passphrase",
        help="Passphrase to encrypt bundle (prompted if not provided)"
    )
    parser.add_argument(
        "--passphrase-file",
        type=Path,
        help="Read passphrase from file (more secure than --passphrase)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output file if it exists"
    )

    args = parser.parse_args()

    # Check if output file exists
    if args.output.exists() and not args.force:
        print(f"✗ Error: Output file already exists: {args.output}")
        print("  Use --force to overwrite")
        sys.exit(1)

    # Get passphrase
    if args.passphrase:
        passphrase = args.passphrase
    elif args.passphrase_file:
        passphrase = args.passphrase_file.read_text().strip()
    else:
        print("Enter passphrase to encrypt key bundle:")
        passphrase = getpass.getpass("Passphrase: ")
        confirm = getpass.getpass("Confirm passphrase: ")

        if passphrase != confirm:
            print("✗ Error: Passphrases do not match")
            sys.exit(1)

    # Validate passphrase strength
    if len(passphrase) < 16:
        print("⚠️  WARNING: Passphrase is less than 16 characters.")
        print("   A strong passphrase is recommended for protecting encryption keys.")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() != "yes":
            print("Export cancelled")
            sys.exit(0)

    # Export keys
    await export_keys(args.output, passphrase)


if __name__ == "__main__":
    asyncio.run(main())
