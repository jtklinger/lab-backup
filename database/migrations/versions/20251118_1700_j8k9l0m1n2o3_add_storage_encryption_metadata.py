"""Add storage encryption metadata tracking

Revision ID: j8k9l0m1n2o3
Revises: i7j8k9l0m1n2
Create Date: 2025-11-18 17:00:00.000000

Implements Issue #12 - Add S3 server-side encryption support

Adds fields to track storage-native encryption (SSE) separate from
app-level encryption:
- storage_encryption_type: NONE, APP_LEVEL, SSE_S3, SSE_KMS, SSE_C
- storage_encryption_key_id: KMS Key ARN for SSE-KMS mode

This allows differentiation between:
1. App-level encryption (encrypt before upload)
2. Storage-native encryption (S3 SSE-S3, SSE-KMS)
3. No encryption
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'j8k9l0m1n2o3'
down_revision = 'i7j8k9l0m1n2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add storage encryption metadata to backups table
    op.add_column('backups', sa.Column(
        'storage_encryption_type',
        sa.String(20),
        nullable=True,
        server_default='NONE',
        comment='Storage-level encryption: NONE, APP_LEVEL, SSE_S3, SSE_KMS, SSE_C'
    ))

    op.add_column('backups', sa.Column(
        'storage_encryption_key_id',
        sa.String(500),
        nullable=True,
        comment='KMS Key ARN for SSE-KMS or customer key identifier for SSE-C'
    ))

    # Create index for encryption type queries
    op.create_index(
        'idx_backups_storage_encryption_type',
        'backups',
        ['storage_encryption_type'],
        unique=False
    )

    # Migrate existing encrypted backups to APP_LEVEL type
    # (backups that have encryption_key_id set used app-level encryption)
    op.execute("""
        UPDATE backups
        SET storage_encryption_type = 'APP_LEVEL'
        WHERE encryption_key_id IS NOT NULL
    """)


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_backups_storage_encryption_type', table_name='backups')

    # Drop columns
    op.drop_column('backups', 'storage_encryption_key_id')
    op.drop_column('backups', 'storage_encryption_type')
