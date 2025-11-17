#!/usr/bin/env python3
"""
Database Restoration Tool

Restores PostgreSQL database from a backup file. This tool supports:
- Encrypted and unencrypted backups
- Local files or downloads from storage backends
- Verification of restoration success
- Automatic backup of current database before restore

Usage:
    python scripts/restore-database.py --file /path/to/backup.sql.gz
    python scripts/restore-database.py --storage s3-backend --latest
    python scripts/restore-database.py --storage local --date 2025-01-15
"""

import argparse
import asyncio
import subprocess
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.config import settings
from backend.core.encryption import decrypt_backup
from backend.models.base import AsyncSessionLocal
from backend.models.storage import StorageBackend as StorageBackendModel
from backend.services.storage import create_storage_backend
from sqlalchemy import select


async def backup_current_database(db_url: str, backup_dir: Path):
    """
    Create a safety backup of the current database before restoring.

    Args:
        db_url: Database connection URL
        backup_dir: Directory to store the safety backup

    Returns:
        Path to the safety backup file
    """
    print("Creating safety backup of current database...")

    parsed = urlparse(db_url)
    db_host = parsed.hostname or "postgres"
    db_port = parsed.port or 5432
    db_user = parsed.username or "labbackup"
    db_name = parsed.path.lstrip('/') or "lab_backup"
    db_password = parsed.password

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    safety_backup = backup_dir / f"safety-backup-{timestamp}.sql.gz"

    env = os.environ.copy()
    if db_password:
        env['PGPASSWORD'] = db_password

    cmd = [
        "pg_dump",
        "-h", db_host,
        "-p", str(db_port),
        "-U", db_user,
        "-d", db_name,
        "-Fc",
        "-f", str(safety_backup)
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"Safety backup failed: {result.stderr}")

    print(f"✓ Safety backup created: {safety_backup}")
    return safety_backup


async def download_backup_from_storage(storage_name: str, backup_date: str = None, latest: bool = False):
    """
    Download database backup from a storage backend.

    Args:
        storage_name: Name of the storage backend
        backup_date: Date of backup to restore (YYYY-MM-DD) or None
        latest: If True, download the latest backup

    Returns:
        Path to downloaded backup file
    """
    print(f"Searching for database backup in storage backend: {storage_name}")

    async with AsyncSessionLocal() as db:
        # Get storage backend
        stmt = select(StorageBackendModel).where(StorageBackendModel.name == storage_name)
        result = await db.execute(stmt)
        backend_model = result.scalar_one_or_none()

        if not backend_model:
            raise Exception(f"Storage backend not found: {storage_name}")

        storage = create_storage_backend(backend_model.type, backend_model.config)

        # List database backups
        backups = await storage.list(prefix="database-backups/", recursive=False)

        if not backups:
            raise Exception("No database backups found in storage")

        # Filter and sort backups
        if backup_date:
            # Filter by date
            filtered = [b for b in backups if backup_date in b.get('name', '')]
            if not filtered:
                raise Exception(f"No backup found for date: {backup_date}")
            backups = filtered

        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x.get('modified', ''), reverse=True)

        if latest or backup_date:
            backup_to_restore = backups[0]
        else:
            # Show available backups and let user choose
            print("\nAvailable backups:")
            for i, backup in enumerate(backups[:10]):  # Show last 10
                print(f"  {i+1}. {backup['name']} ({backup.get('size', 0) // 1024 // 1024} MB)")

            choice = input("\nSelect backup number to restore (or 'q' to quit): ")
            if choice.lower() == 'q':
                sys.exit(0)

            try:
                idx = int(choice) - 1
                backup_to_restore = backups[idx]
            except (ValueError, IndexError):
                raise Exception("Invalid selection")

        print(f"\nDownloading: {backup_to_restore['name']}")

        # Download to temporary directory
        temp_dir = Path(tempfile.mkdtemp())
        download_path = temp_dir / backup_to_restore['name']

        await storage.download(
            source_path=backup_to_restore['name'],
            destination_path=download_path
        )

        print(f"✓ Downloaded to: {download_path}")
        return download_path


async def restore_database(backup_file: Path, db_url: str, encrypted: bool = False):
    """
    Restore PostgreSQL database from backup file.

    Args:
        backup_file: Path to backup file
        db_url: Database connection URL
        encrypted: Whether the backup is encrypted
    """
    parsed = urlparse(db_url)
    db_host = parsed.hostname or "postgres"
    db_port = parsed.port or 5432
    db_user = parsed.username or "labbackup"
    db_name = parsed.path.lstrip('/') or "lab_backup"
    db_password = parsed.password

    # Decrypt if needed
    file_to_restore = backup_file

    if encrypted:
        if not settings.ENCRYPTION_KEY:
            raise Exception("Backup is encrypted but ENCRYPTION_KEY not available")

        print("Decrypting backup...")
        decrypted_file = backup_file.parent / backup_file.name.replace('.encrypted', '')

        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: decrypt_backup(
                backup_file,
                decrypted_file,
                settings.ENCRYPTION_KEY,
                use_chunked=False
            )
        )

        file_to_restore = decrypted_file
        print("✓ Backup decrypted")

    # Drop existing connections to database
    print(f"Terminating existing connections to database: {db_name}")

    env = os.environ.copy()
    if db_password:
        env['PGPASSWORD'] = db_password

    terminate_cmd = [
        "psql",
        "-h", db_host,
        "-p", str(db_port),
        "-U", db_user,
        "-d", "postgres",
        "-c", f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid != pg_backend_pid();"
    ]

    subprocess.run(terminate_cmd, env=env, capture_output=True)

    # Drop and recreate database
    print(f"Dropping and recreating database: {db_name}")

    drop_cmd = [
        "psql",
        "-h", db_host,
        "-p", str(db_port),
        "-U", db_user,
        "-d", "postgres",
        "-c", f"DROP DATABASE IF EXISTS {db_name};"
    ]

    result = subprocess.run(drop_cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to drop database: {result.stderr}")

    create_cmd = [
        "psql",
        "-h", db_host,
        "-p", str(db_port),
        "-U", db_user,
        "-d", "postgres",
        "-c", f"CREATE DATABASE {db_name};"
    ]

    result = subprocess.run(create_cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to create database: {result.stderr}")

    # Restore database from backup
    print("Restoring database from backup...")

    restore_cmd = [
        "pg_restore",
        "-h", db_host,
        "-p", str(db_port),
        "-U", db_user,
        "-d", db_name,
        "-v",  # Verbose
        str(file_to_restore)
    ]

    result = subprocess.run(restore_cmd, env=env, capture_output=True, text=True)

    # pg_restore returns non-zero even for warnings, so check stderr for actual errors
    if "error" in result.stderr.lower() and result.returncode != 0:
        raise Exception(f"Database restore failed: {result.stderr}")

    print("✓ Database restored successfully")

    # Verify restoration
    print("\nVerifying restoration...")

    verify_cmd = [
        "psql",
        "-h", db_host,
        "-p", str(db_port),
        "-U", db_user,
        "-d", db_name,
        "-c", "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
    ]

    result = subprocess.run(verify_cmd, env=env, capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ Database verification passed")
        print(f"  Tables restored: {result.stdout.strip()}")
    else:
        print("⚠ Warning: Could not verify database restoration")


async def main():
    parser = argparse.ArgumentParser(
        description="Restore PostgreSQL database from backup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Backup source options
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--file",
        type=Path,
        help="Path to local backup file"
    )
    source_group.add_argument(
        "--storage",
        help="Name of storage backend to download from"
    )

    # Storage options
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Restore latest backup from storage (use with --storage)"
    )
    parser.add_argument(
        "--date",
        help="Restore backup from specific date YYYY-MM-DD (use with --storage)"
    )

    # Other options
    parser.add_argument(
        "--encrypted",
        action="store_true",
        help="Backup file is encrypted"
    )
    parser.add_argument(
        "--no-safety-backup",
        action="store_true",
        help="Skip creating safety backup of current database"
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompts"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.file and (args.latest or args.date):
        parser.error("--latest and --date can only be used with --storage")

    print("=" * 60)
    print("DATABASE RESTORATION TOOL")
    print("=" * 60)
    print()

    # Get backup file
    if args.file:
        backup_file = args.file
        if not backup_file.exists():
            print(f"Error: Backup file not found: {backup_file}")
            sys.exit(1)
    else:
        backup_file = await download_backup_from_storage(
            args.storage,
            backup_date=args.date,
            latest=args.latest
        )
        args.encrypted = backup_file.name.endswith('.encrypted')

    print(f"\nBackup file: {backup_file}")
    print(f"Encrypted: {args.encrypted}")
    print(f"Database: {settings.DATABASE_URL}")
    print()

    # Confirmation
    if not args.yes:
        confirm = input("⚠️  This will REPLACE the current database. Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("Restoration cancelled")
            sys.exit(0)

    try:
        # Create safety backup
        if not args.no_safety_backup:
            temp_dir = Path(tempfile.mkdtemp())
            safety_backup = await backup_current_database(str(settings.DATABASE_URL), temp_dir)
            print(f"\n⚠️  Safety backup saved to: {safety_backup}")
            print("   Keep this file until you verify the restoration!\n")

        # Restore database
        await restore_database(backup_file, str(settings.DATABASE_URL), args.encrypted)

        print("\n" + "=" * 60)
        print("✓ DATABASE RESTORATION COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Restart the application services")
        print("2. Verify application functionality")
        print("3. Check that backups can be decrypted")
        if not args.no_safety_backup:
            print(f"4. Delete safety backup if restoration is successful: {safety_backup}")

    except Exception as e:
        print(f"\n✗ ERROR: {e}", file=sys.stderr)
        if not args.no_safety_backup:
            print(f"\n⚠️  You can restore from safety backup: {safety_backup}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
