"""Add Changed Block Tracking (CBT) support

Revision ID: f4e5d6c7b8a9
Revises: a8b9c0d1e2f3
Create Date: 2025-11-18 11:07:00.000000

Implements Issue #15 - Changed Block Tracking (CBT)

Adds fields to track QEMU dirty bitmaps for efficient incremental backups.

Changes to VMs table:
- cbt_enabled: Whether CBT is enabled for this VM
- dirty_bitmap_name: Name of the active dirty bitmap
- qemu_version: Detected QEMU version string
- cbt_capable: Whether the hypervisor supports CBT

Changes to backups table:
- changed_blocks_count: Number of changed blocks in incremental backup
- cbt_enabled: Whether this backup used CBT
- bitmap_name: Name of the bitmap used for this backup
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'f4e5d6c7b8a9'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add CBT tracking to VMs table
    op.add_column('vms', sa.Column(
        'cbt_enabled',
        sa.Boolean(),
        nullable=False,
        server_default='false',
        comment='Whether Changed Block Tracking is enabled for this VM'
    ))

    op.add_column('vms', sa.Column(
        'dirty_bitmap_name',
        sa.String(255),
        nullable=True,
        comment='Name of the active dirty bitmap for CBT'
    ))

    op.add_column('vms', sa.Column(
        'qemu_version',
        sa.String(50),
        nullable=True,
        comment='Detected QEMU version (e.g., "4.2.1")'
    ))

    op.add_column('vms', sa.Column(
        'cbt_capable',
        sa.Boolean(),
        nullable=True,
        comment='Whether hypervisor supports CBT (QEMU >= 4.0)'
    ))

    # Add CBT tracking to backups table
    op.add_column('backups', sa.Column(
        'changed_blocks_count',
        sa.BigInteger(),
        nullable=True,
        comment='Number of changed blocks in incremental backup (0 for full backups)'
    ))

    op.add_column('backups', sa.Column(
        'cbt_enabled',
        sa.Boolean(),
        nullable=False,
        server_default='false',
        comment='Whether this backup used CBT for incremental tracking'
    ))

    op.add_column('backups', sa.Column(
        'bitmap_name',
        sa.String(255),
        nullable=True,
        comment='Name of the dirty bitmap used for this backup'
    ))

    op.add_column('backups', sa.Column(
        'block_size',
        sa.Integer(),
        nullable=True,
        comment='Block size (granularity) used for CBT tracking (bytes)'
    ))

    # Create index for CBT-enabled VMs
    op.create_index(
        'idx_vms_cbt_enabled',
        'vms',
        ['cbt_enabled'],
        unique=False
    )

    # Create index for CBT backups
    op.create_index(
        'idx_backups_cbt_enabled',
        'backups',
        ['cbt_enabled'],
        unique=False
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_backups_cbt_enabled', table_name='backups')
    op.drop_index('idx_vms_cbt_enabled', table_name='vms')

    # Drop columns from backups table
    op.drop_column('backups', 'block_size')
    op.drop_column('backups', 'bitmap_name')
    op.drop_column('backups', 'cbt_enabled')
    op.drop_column('backups', 'changed_blocks_count')

    # Drop columns from vms table
    op.drop_column('vms', 'cbt_capable')
    op.drop_column('vms', 'qemu_version')
    op.drop_column('vms', 'dirty_bitmap_name')
    op.drop_column('vms', 'cbt_enabled')
