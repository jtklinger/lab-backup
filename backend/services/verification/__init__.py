"""
Backup Verification Services

This package provides automated backup verification capabilities using
isolated test pods. Backups are verified by restoring them to temporary
PostgreSQL containers and validating the restoration.
"""

from backend.services.verification.recovery_test import (
    RecoveryTestService,
    RecoveryTestError
)

__all__ = [
    'RecoveryTestService',
    'RecoveryTestError'
]
