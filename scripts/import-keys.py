#!/usr/bin/env python3
"""
Encryption Key Import Tool

Imports encryption keys from an encrypted bundle created by export-keys.py.
This is used during disaster recovery to restore encryption keys to a
fresh database installation.

Usage:
    python scripts/import-keys.py --input keys-backup.encrypted
    python scripts/import-keys.py --input keys-backup.encrypted --verify-only
    python scripts/import-keys.py --input keys-backup.encrypted --passphrase-file /secure/passphrase.txt

Security:
    - Bundle must be decrypted with the correct passphrase
    - Keys are re-encrypted with current master KEK from .env
    - Existing keys in database will NOT be overwritten by default
"""

import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path
from datetime import datetime
from cryptography.fernet import Fernet, InvalidToken
import hashlib

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.base import AsyncSessionLocal
from backend.services.key_management import KeyManagementService


def derive_key_from_passphrase(passphrase: str) -> bytes:
    """
    Derive a Fernet key from a user passphrase using PBKDF2.

    Must match the derivation in export-keys.py.

    Args:
        passphrase: User-provided passphrase

    Returns:
        32-byte Fernet-compatible key (base64-encoded)
    """
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    # Use same fixed salt as export
    salt = b"lab-backup-key-export-v1"

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )

    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode('utf-8')))
    return key


def decrypt_bundle(encrypted_data: bytes, passphrase: str) -> dict:
    """
    Decrypt key bundle with user passphrase.

    Args:
        encrypted_data: Encrypted bundle bytes
        passphrase: User-provided passphrase

    Returns:
        Decrypted bundle dictionary

    Raises:
        InvalidToken: If passphrase is incorrect
    """
    # Derive encryption key from passphrase
    encryption_key = derive_key_from_passphrase(passphrase)

    # Decrypt with Fernet
    fernet = Fernet(encryption_key)
    try:
        decrypted = fernet.decrypt(encrypted_data)
        return json.loads(decrypted.decode('utf-8'))
    except InvalidToken:
        raise ValueError("Incorrect passphrase or corrupted bundle")


async def import_keys(
    input_path: Path,
    passphrase: str,
    verify_only: bool = False,
    overwrite: bool = False
):
    """
    Import encryption keys from encrypted bundle.

    Args:
        input_path: Path to encrypted bundle
        passphrase: Passphrase to decrypt bundle
        verify_only: If True, only verify bundle without importing
        overwrite: If True, overwrite existing keys
    """
    print("=" * 70)
    print("ENCRYPTION KEY IMPORT TOOL")
    print("=" * 70)
    print()

    # Read encrypted bundle
    print(f"Reading encrypted bundle: {input_path}")
    encrypted_data = input_path.read_bytes()
    checksum = hashlib.sha256(encrypted_data).hexdigest()
    print(f"  File Size: {len(encrypted_data)} bytes")
    print(f"  SHA256: {checksum}")
    print()

    # Decrypt bundle
    print("Decrypting bundle with passphrase...")
    try:
        bundle = decrypt_bundle(encrypted_data, passphrase)
        print("✓ Bundle decrypted successfully")
    except ValueError as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

    # Validate bundle format
    if bundle.get('version') != 1:
        print(f"✗ Error: Unsupported bundle version: {bundle.get('version')}")
        sys.exit(1)

    # Display bundle information
    print()
    print("Bundle Information:")
    print(f"  Export Date: {bundle.get('export_date')}")
    print(f"  Key Count: {bundle.get('key_count')}")
    print()

    keys_data = bundle.get('keys', [])
    if not keys_data:
        print("✗ Error: No keys found in bundle")
        sys.exit(1)

    # Show key breakdown
    print("Keys in Bundle:")
    key_types = {}
    for key in keys_data:
        key_type = key['key_type']
        key_types[key_type] = key_types.get(key_type, 0) + 1

    for key_type, count in sorted(key_types.items()):
        active_count = sum(1 for k in keys_data if k['key_type'] == key_type and k['active'])
        print(f"  {key_type.upper()}: {count} total ({active_count} active)")
    print()

    if verify_only:
        print("=" * 70)
        print("✓ VERIFICATION SUCCESSFUL")
        print("=" * 70)
        print()
        print("Bundle is valid and can be decrypted with the provided passphrase.")
        print("Keys have NOT been imported (--verify-only flag was used).")
        print()
        print("To import these keys:")
        print(f"  python scripts/import-keys.py --input {input_path}")
        print()
        return

    # Import keys to database
    async with AsyncSessionLocal() as db:
        try:
            print("Connecting to database...")
            key_service = KeyManagementService(db)

            # Check for existing keys
            existing_keys = await key_service.list_all_keys()

            if existing_keys and not overwrite:
                print()
                print("⚠️  WARNING: Database already contains encryption keys:")
                print(f"   Existing keys: {len(existing_keys)}")
                print(f"   Keys to import: {len(keys_data)}")
                print()
                print("Importing will ADD these keys to the existing ones.")
                print("This may cause conflicts if keys already exist.")
                print()
                response = input("Continue with import? (yes/no): ")
                if response.lower() != "yes":
                    print("Import cancelled")
                    sys.exit(0)

            # Import keys (re-encrypt with current master KEK)
            print()
            print(f"Importing {len(keys_data)} keys...")
            imported_count = await key_service.import_keys_from_backup(
                keys_data,
                reencrypt_with_current_kek=True
            )

            print()
            print("=" * 70)
            print("✓ IMPORT SUCCESSFUL")
            print("=" * 70)
            print()
            print(f"Import Summary:")
            print(f"  Keys Imported: {imported_count}")
            print(f"  Import Date: {datetime.utcnow().isoformat()}")
            print()
            print("Next Steps:")
            print()
            print("1. Verify keys are working:")
            print("   - Try decrypting an existing backup")
            print("   - Check encryption key status in database")
            print()
            print("2. Test backup operations:")
            print("   - Create a test backup")
            print("   - Verify the backup can be decrypted")
            print()
            print("3. Update disaster recovery documentation:")
            print("   - Document when keys were imported")
            print("   - Update key export/import procedures")
            print()

        except Exception as e:
            print(f"\n✗ ERROR: Import failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(
        description="Import encryption keys from encrypted bundle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to encrypted key bundle"
    )
    parser.add_argument(
        "--passphrase",
        help="Passphrase to decrypt bundle (prompted if not provided)"
    )
    parser.add_argument(
        "--passphrase-file",
        type=Path,
        help="Read passphrase from file (more secure than --passphrase)"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify bundle can be decrypted, don't import"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing keys in database (DANGEROUS)"
    )

    args = parser.parse_args()

    # Check if input file exists
    if not args.input.exists():
        print(f"✗ Error: Input file not found: {args.input}")
        sys.exit(1)

    # Get passphrase
    if args.passphrase:
        passphrase = args.passphrase
    elif args.passphrase_file:
        if not args.passphrase_file.exists():
            print(f"✗ Error: Passphrase file not found: {args.passphrase_file}")
            sys.exit(1)
        passphrase = args.passphrase_file.read_text().strip()
    else:
        print("Enter passphrase to decrypt key bundle:")
        passphrase = getpass.getpass("Passphrase: ")

    # Import keys
    await import_keys(
        args.input,
        passphrase,
        verify_only=args.verify_only,
        overwrite=args.overwrite
    )


if __name__ == "__main__":
    asyncio.run(main())
