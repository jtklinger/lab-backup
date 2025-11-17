#!/usr/bin/env python3
"""
Database Backup Verification Tool

Verifies the integrity and recoverability of database backups without actually
performing a restoration. This tool:
- Checks file integrity (exists, readable, correct format)
- Verifies encryption (can be decrypted if encrypted)
- Tests pg_restore --list (validates backup structure)
- Reports on backup metadata

Usage:
    python scripts/verify-database-backup.py --file /path/to/backup.sql.gz
    python scripts/verify-database-backup.py --storage s3-backend --all
    python scripts/verify-database-backup.py --storage local --latest
"""

import argparse
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.config import settings
from backend.core.encryption import decrypt_backup
from backend.models.base import AsyncSessionLocal
from backend.models.storage import StorageBackend as StorageBackendModel
from backend.services.storage import create_storage_backend
from sqlalchemy import select


class BackupVerificationResult:
    """Container for verification results."""

    def __init__(self, backup_name: str):
        self.backup_name = backup_name
        self.file_exists = False
        self.file_size = 0
        self.encrypted = False
        self.can_decrypt = False
        self.valid_format = False
        self.table_count = 0
        self.schema_count = 0
        self.errors = []
        self.warnings = []

    def is_valid(self) -> bool:
        """Check if backup passed all critical validations."""
        return (
            self.file_exists and
            self.valid_format and
            not self.errors and
            (not self.encrypted or self.can_decrypt)
        )

    def print_report(self):
        """Print verification report."""
        print("\n" + "=" * 70)
        print(f"VERIFICATION REPORT: {self.backup_name}")
        print("=" * 70)

        status = "✓ PASS" if self.is_valid() else "✗ FAIL"
        print(f"\nOverall Status: {status}\n")

        print("Checks:")
        print(f"  {'✓' if self.file_exists else '✗'} File exists and readable")
        print(f"  {'✓' if self.valid_format else '✗'} Valid PostgreSQL backup format")

        if self.encrypted:
            print(f"  {'✓' if self.can_decrypt else '✗'} Encrypted backup can be decrypted")

        if self.valid_format:
            print(f"\nBackup Contents:")
            print(f"  Tables: {self.table_count}")
            print(f"  Schemas: {self.schema_count}")
            print(f"  Size: {self.file_size / 1024 / 1024:.2f} MB")

        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")

        if self.errors:
            print(f"\n✗ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")

        print("=" * 70)


async def verify_backup_file(backup_file: Path, encrypted: bool = False) -> BackupVerificationResult:
    """
    Verify a database backup file.

    Args:
        backup_file: Path to backup file
        encrypted: Whether backup is encrypted

    Returns:
        BackupVerificationResult with verification results
    """
    result = BackupVerificationResult(backup_file.name)

    # Check file exists
    if not backup_file.exists():
        result.errors.append(f"File not found: {backup_file}")
        return result

    result.file_exists = True
    result.file_size = backup_file.stat().st_size
    result.encrypted = encrypted

    if result.file_size == 0:
        result.errors.append("File is empty")
        return result

    # Decrypt if needed
    file_to_verify = backup_file

    if encrypted:
        if not settings.ENCRYPTION_KEY:
            result.errors.append("Backup is encrypted but ENCRYPTION_KEY not available")
            return result

        try:
            print(f"  Decrypting backup...")
            temp_dir = Path(tempfile.mkdtemp())
            decrypted_file = temp_dir / backup_file.name.replace('.encrypted', '')

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: decrypt_backup(
                    backup_file,
                    decrypted_file,
                    settings.ENCRYPTION_KEY,
                    use_chunked=False
                )
            )

            file_to_verify = decrypted_file
            result.can_decrypt = True
            print(f"  ✓ Decryption successful")

        except Exception as e:
            result.errors.append(f"Decryption failed: {e}")
            return result

    # Verify backup format using pg_restore --list
    print(f"  Validating backup structure...")

    try:
        list_cmd = [
            "pg_restore",
            "--list",
            str(file_to_verify)
        ]

        proc = subprocess.run(
            list_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if proc.returncode != 0:
            result.errors.append(f"pg_restore failed: {proc.stderr}")
            return result

        result.valid_format = True

        # Parse output to count tables and schemas
        output = proc.stdout

        # Count table entries
        result.table_count = output.count('TABLE DATA')

        # Count schemas
        result.schema_count = output.count('SCHEMA')

        # Look for potential issues
        if 'ERROR' in output:
            result.warnings.append("Backup contains error markers")

        if result.table_count == 0:
            result.warnings.append("No tables found in backup")

        print(f"  ✓ Backup structure validated ({result.table_count} tables)")

    except subprocess.TimeoutExpired:
        result.errors.append("pg_restore validation timed out")
    except Exception as e:
        result.errors.append(f"Validation failed: {e}")

    return result


async def list_storage_backups(storage_name: str):
    """
    List all database backups in a storage backend.

    Args:
        storage_name: Name of storage backend

    Returns:
        List of backup information dictionaries
    """
    async with AsyncSessionLocal() as db:
        stmt = select(StorageBackendModel).where(StorageBackendModel.name == storage_name)
        result = await db.execute(stmt)
        backend_model = result.scalar_one_or_none()

        if not backend_model:
            raise Exception(f"Storage backend not found: {storage_name}")

        storage = create_storage_backend(backend_model.type, backend_model.config)

        backups = await storage.list(prefix="database-backups/", recursive=False)

        # Sort by modified date (newest first)
        backups.sort(key=lambda x: x.get('modified', ''), reverse=True)

        return backups


async def verify_storage_backup(storage_name: str, backup_name: str) -> BackupVerificationResult:
    """
    Download and verify a backup from storage.

    Args:
        storage_name: Name of storage backend
        backup_name: Name of backup file

    Returns:
        BackupVerificationResult
    """
    print(f"\nDownloading backup: {backup_name}")

    async with AsyncSessionLocal() as db:
        stmt = select(StorageBackendModel).where(StorageBackendModel.name == storage_name)
        result = await db.execute(stmt)
        backend_model = result.scalar_one_or_none()

        if not backend_model:
            raise Exception(f"Storage backend not found: {storage_name}")

        storage = create_storage_backend(backend_model.type, backend_model.config)

        # Download to temp directory
        temp_dir = Path(tempfile.mkdtemp())
        download_path = temp_dir / Path(backup_name).name

        await storage.download(
            source_path=backup_name,
            destination_path=download_path
        )

        print(f"  Downloaded to: {download_path}")

        # Check if encrypted
        encrypted = download_path.name.endswith('.encrypted')

        # Verify
        return await verify_backup_file(download_path, encrypted=encrypted)


async def main():
    parser = argparse.ArgumentParser(
        description="Verify PostgreSQL database backup integrity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Backup source options
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--file",
        type=Path,
        help="Path to local backup file to verify"
    )
    source_group.add_argument(
        "--storage",
        help="Name of storage backend to verify backups from"
    )

    # Storage options
    parser.add_argument(
        "--all",
        action="store_true",
        help="Verify all backups in storage (use with --storage)"
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Verify only latest backup in storage (use with --storage)"
    )
    parser.add_argument(
        "--encrypted",
        action="store_true",
        help="Backup file is encrypted (use with --file)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.file and (args.all or args.latest):
        parser.error("--all and --latest can only be used with --storage")

    print("=" * 70)
    print("DATABASE BACKUP VERIFICATION TOOL")
    print("=" * 70)

    results = []

    try:
        if args.file:
            # Verify single local file
            print(f"\nVerifying local file: {args.file}")
            result = await verify_backup_file(args.file, encrypted=args.encrypted)
            results.append(result)

        else:
            # Verify backups from storage
            backups = await list_storage_backups(args.storage)

            if not backups:
                print(f"\n✗ No backups found in storage: {args.storage}")
                sys.exit(1)

            print(f"\nFound {len(backups)} backup(s) in storage")

            # Determine which backups to verify
            if args.latest:
                backups_to_verify = [backups[0]]
            elif args.all:
                backups_to_verify = backups
            else:
                # Interactive selection
                print("\nAvailable backups:")
                for i, backup in enumerate(backups[:10]):
                    modified = backup.get('modified', 'unknown')
                    size = backup.get('size', 0) // 1024 // 1024
                    print(f"  {i+1}. {backup['name']} ({size} MB, {modified})")

                choice = input("\nSelect backup number to verify (or 'a' for all, 'q' to quit): ")

                if choice.lower() == 'q':
                    sys.exit(0)
                elif choice.lower() == 'a':
                    backups_to_verify = backups
                else:
                    try:
                        idx = int(choice) - 1
                        backups_to_verify = [backups[idx]]
                    except (ValueError, IndexError):
                        print("Invalid selection")
                        sys.exit(1)

            # Verify selected backups
            for backup_info in backups_to_verify:
                result = await verify_storage_backup(args.storage, backup_info['name'])
                results.append(result)

        # Print individual reports
        for result in results:
            result.print_report()

        # Summary
        if len(results) > 1:
            total = len(results)
            passed = sum(1 for r in results if r.is_valid())
            failed = total - passed

            print("\n" + "=" * 70)
            print("SUMMARY")
            print("=" * 70)
            print(f"Total backups verified: {total}")
            print(f"Passed: {passed}")
            print(f"Failed: {failed}")
            print("=" * 70)

            if failed > 0:
                sys.exit(1)

        # Exit code
        if any(not r.is_valid() for r in results):
            sys.exit(1)

    except Exception as e:
        print(f"\n✗ ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
