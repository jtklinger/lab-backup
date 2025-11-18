"""Add per-storage-backend encryption keys

Revision ID: h6i7j8k9l0m1
Revises: g5h6i7j8k9l0
Create Date: 2025-11-18 15:30:00.000000

Implements Issue #11 - Implement per-storage-backend encryption keys

Extends the encryption key infrastructure (Issue #7) to support:
- Different encryption keys per storage backend
- Per-VM encryption keys (future)
- Encryption strategy selection (app-level, storage-native, disabled)
- Key rotation per storage backend

Changes to storage_backends table:
- encryption_strategy: Strategy for this backend (DISABLED, APP_LEVEL, STORAGE_NATIVE)
- encryption_key_id: FK to encryption_keys table for app-level encryption
- encryption_config: JSONB for encryption-specific configuration

This enables:
- Security isolation between storage backends
- Multi-tenant support with separate keys
- Integration with cloud-native encryption (S3 SSE, etc.)
- Key rotation without re-encrypting all backups
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = 'h6i7j8k9l0m1'
down_revision = 'g5h6i7j8k9l0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add encryption strategy to storage_backends table
    op.add_column('storage_backends', sa.Column(
        'encryption_strategy',
        sa.String(50),
        nullable=False,
        server_default='DISABLED',
        comment='Encryption strategy: DISABLED, APP_LEVEL, STORAGE_NATIVE, GLOBAL'
    ))

    op.add_column('storage_backends', sa.Column(
        'encryption_key_id',
        sa.Integer(),
        sa.ForeignKey('encryption_keys.id', ondelete='RESTRICT'),
        nullable=True,
        comment='Encryption key for APP_LEVEL strategy (FK to encryption_keys)'
    ))

    op.add_column('storage_backends', sa.Column(
        'encryption_config',
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        comment='Encryption configuration (SSE-KMS ARN, etc.)'
    ))

    # Create index for encryption key lookups
    op.create_index(
        'idx_storage_backends_encryption_key_id',
        'storage_backends',
        ['encryption_key_id'],
        unique=False
    )

    # Migrate existing storage backends to use GLOBAL strategy
    # This maintains backward compatibility with existing deployments
    op.execute("""
        UPDATE storage_backends
        SET encryption_strategy = 'GLOBAL'
        WHERE encryption_strategy = 'DISABLED'
    """)


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_storage_backends_encryption_key_id', table_name='storage_backends')

    # Drop columns
    op.drop_column('storage_backends', 'encryption_config')
    op.drop_column('storage_backends', 'encryption_key_id')
    op.drop_column('storage_backends', 'encryption_strategy')
