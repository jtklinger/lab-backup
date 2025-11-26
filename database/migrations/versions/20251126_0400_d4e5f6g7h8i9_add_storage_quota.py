"""Add quota_gb column to storage_backends

Revision ID: d4e5f6g7h8i9
Revises: c2d3e4f5g6h7
Create Date: 2025-11-26 04:00:00.000000

Adds quota_gb column to storage_backends table for manual storage quota limits.
This is used for S3/SMB backends where capacity cannot be auto-detected.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'd4e5f6g7h8i9'
down_revision = 'c2d3e4f5g6h7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add quota_gb column for manual storage quota limits
    # This is used for S3/SMB backends where capacity cannot be auto-detected
    # For Local storage, capacity is auto-detected from the filesystem
    op.add_column('storage_backends', sa.Column(
        'quota_gb',
        sa.Integer(),
        nullable=True,
        comment='Manual storage quota limit in GB (for S3/SMB where capacity cannot be auto-detected)'
    ))


def downgrade() -> None:
    op.drop_column('storage_backends', 'quota_gb')
