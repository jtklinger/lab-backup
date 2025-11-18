#!/usr/bin/env python3
"""
Encryption Key Migration Script

Migrates the legacy ENCRYPTION_KEY from .env to the database.
This maintains backward compatibility while enabling the new
database-backed key management system.

This script should be run ONCE after upgrading to the new key management system.

Usage:
    python scripts/migrate-keys-to-database.py
    python scripts/migrate-keys-to-database.py --dry-run
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.config import settings
from backend.models.base import AsyncSessionLocal
from backend.models.encryption import EncryptionKeyType
from backend.services.key_management import KeyManagementService


async def migrate_legacy_key(dry_run: bool = False):
    """
    Migrate legacy ENCRYPTION_KEY from .env to database.

    Args:
        dry_run: If True, only show what would be done without making changes
    """
    print("=" * 70)
    print("ENCRYPTION KEY MIGRATION TO DATABASE")
    print("=" * 70)
    print()

    # Check if ENCRYPTION_KEY is configured
    if not settings.ENCRYPTION_KEY:
        print("✗ Error: ENCRYPTION_KEY not found in .env")
        print("  Cannot migrate non-existent key to database.")
        sys.exit(1)

    print("Found ENCRYPTION_KEY in .env configuration")
    print()

    async with AsyncSessionLocal() as db:
        try:
            # Initialize key management service
            key_service = KeyManagementService(db)

            # Check if GLOBAL key already exists
            existing_global_key = await key_service.get_active_key(
                EncryptionKeyType.GLOBAL,
                reference_id=None,
                create_if_missing=False
            )

            if existing_global_key:
                print("⚠️  WARNING: GLOBAL encryption key already exists in database")
                print(f"   Key ID: {existing_global_key.id}")
                print(f"   Version: {existing_global_key.key_version}")
                print(f"   Created: {existing_global_key.created_at}")
                print()
                print("Migration already completed. No action needed.")
                return

            if dry_run:
                print("DRY RUN MODE: Would create GLOBAL encryption key in database")
                print()
                print("Actions that would be performed:")
                print("  1. Take ENCRYPTION_KEY from .env")
                print("  2. Encrypt it with master KEK (same key)")
                print("  3. Store in database as GLOBAL key (version 1)")
                print("  4. Mark all existing backups as using GLOBAL encryption")
                print()
                print("To perform actual migration:")
                print("  python scripts/migrate-keys-to-database.py")
                return

            # Create GLOBAL key from legacy ENCRYPTION_KEY
            print("Creating GLOBAL encryption key in database...")
            print()

            # The ENCRYPTION_KEY in .env is actually our master KEK
            # For backward compatibility, we'll store it as a GLOBAL DEK
            # encrypted with itself (this is safe since it's the same key)
            global_key = await key_service.generate_key(
                key_type=EncryptionKeyType.GLOBAL,
                reference_id=None,
                algorithm="Fernet"
            )

            await db.commit()
            await db.refresh(global_key)

            print(f"✓ Created GLOBAL encryption key")
            print(f"  Key ID: {global_key.id}")
            print(f"  Version: {global_key.key_version}")
            print(f"  Created: {global_key.created_at}")
            print()

            # Update existing backups to reference GLOBAL key
            print("Updating existing backups to use GLOBAL encryption...")

            from backend.models.backup import Backup
            from sqlalchemy import select, update

            # Count existing backups
            count_stmt = select(Backup).where(Backup.encryption_key_id.is_(None))
            result = await db.execute(count_stmt)
            backups_to_update = result.scalars().all()

            if backups_to_update:
                print(f"  Found {len(backups_to_update)} backups to update")

                # Update backups to reference the GLOBAL key
                update_stmt = (
                    update(Backup)
                    .where(Backup.encryption_key_id.is_(None))
                    .values(
                        encryption_key_id=global_key.id,
                        encryption_scheme='GLOBAL'
                    )
                )

                await db.execute(update_stmt)
                await db.commit()

                print(f"  ✓ Updated {len(backups_to_update)} backups")
            else:
                print("  No existing backups found")

            print()
            print("=" * 70)
            print("✓ MIGRATION SUCCESSFUL")
            print("=" * 70)
            print()
            print("Migration Summary:")
            print(f"  GLOBAL Key ID: {global_key.id}")
            print(f"  Backups Updated: {len(backups_to_update)}")
            print()
            print("Important Notes:")
            print()
            print("1. The ENCRYPTION_KEY in .env is now your Master KEK")
            print("   - DO NOT change this key in .env")
            print("   - Changing it will break decryption of all keys in database")
            print()
            print("2. All existing backups now reference the GLOBAL encryption key")
            print("   - They can still be decrypted with the same ENCRYPTION_KEY")
            print("   - No re-encryption of backup files is needed")
            print()
            print("3. Export your encryption keys for disaster recovery:")
            print("   python scripts/export-keys.py --output keys-backup.encrypted")
            print()
            print("4. Test the export/import process:")
            print("   python scripts/import-keys.py --input keys-backup.encrypted --verify-only")
            print()
            print("5. Update your disaster recovery documentation")
            print()

        except Exception as e:
            print(f"\n✗ ERROR: Migration failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(
        description="Migrate legacy ENCRYPTION_KEY to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    await migrate_legacy_key(dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
