"""Add incremental backup configuration to backup_schedules

Revision ID: c2d3e4f5g6h7
Revises: b1c2d3e4f5g6
Create Date: 2025-11-24 21:00:00.000000

Adds columns to backup_schedules table for incremental backup configuration:
- backup_mode_policy: How to determine full vs incremental (auto/full_only/incremental_preferred)
- max_chain_length: Maximum number of incrementals before forcing a full backup
- full_backup_day: Day of week (0-6) or month (1-31) for scheduled full backups
- last_full_backup_id: Reference to the most recent full backup in the chain
- checkpoint_name: Current libvirt checkpoint name for incremental tracking

Related: Issue #15 - Implement Changed Block Tracking (CBT)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'c2d3e4f5g6h7'
down_revision = 'b1c2d3e4f5g6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add backup mode policy - how to determine if backup should be full or incremental
    # Values: 'auto' (system decides based on chain length and schedule)
    #         'full_only' (always full backups)
    #         'incremental_preferred' (incremental when possible, full when required)
    op.add_column('backup_schedules', sa.Column(
        'backup_mode_policy',
        sa.String(30),
        nullable=False,
        server_default='auto',
        comment='Backup mode policy: auto, full_only, or incremental_preferred'
    ))

    # Maximum number of incremental backups in a chain before forcing a full backup
    # Default of 14 means weekly full + daily incrementals for 2 weeks
    op.add_column('backup_schedules', sa.Column(
        'max_chain_length',
        sa.Integer(),
        nullable=False,
        server_default='14',
        comment='Maximum incremental backups before forcing a full backup'
    ))

    # Day to always perform full backup (for predictable consolidation)
    # For weekly schedules: 0=Monday, 6=Sunday
    # For monthly schedules: 1-31 (day of month)
    # NULL means no fixed full backup day (use max_chain_length only)
    op.add_column('backup_schedules', sa.Column(
        'full_backup_day',
        sa.Integer(),
        nullable=True,
        comment='Day for scheduled full backups (0-6 for weekly, 1-31 for monthly)'
    ))

    # Reference to the last full backup for this schedule (start of current chain)
    op.add_column('backup_schedules', sa.Column(
        'last_full_backup_id',
        sa.Integer(),
        sa.ForeignKey('backups.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
        comment='ID of the most recent full backup (chain anchor)'
    ))

    # Current checkpoint name used for incremental tracking
    # This is the libvirt checkpoint created after the last backup
    op.add_column('backup_schedules', sa.Column(
        'checkpoint_name',
        sa.String(255),
        nullable=True,
        comment='Current libvirt checkpoint name for dirty bitmap tracking'
    ))

    # Track incremental capability status for the VM/hypervisor
    # Helps avoid repeated capability checks on each backup
    op.add_column('backup_schedules', sa.Column(
        'incremental_capable',
        sa.Boolean(),
        nullable=True,
        comment='Whether the VM/hypervisor supports incremental backups (cached)'
    ))

    # Last time incremental capability was checked
    op.add_column('backup_schedules', sa.Column(
        'capability_checked_at',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='When incremental capability was last verified'
    ))


def downgrade() -> None:
    op.drop_column('backup_schedules', 'capability_checked_at')
    op.drop_column('backup_schedules', 'incremental_capable')
    op.drop_column('backup_schedules', 'checkpoint_name')
    op.drop_column('backup_schedules', 'last_full_backup_id')
    op.drop_column('backup_schedules', 'full_backup_day')
    op.drop_column('backup_schedules', 'max_chain_length')
    op.drop_column('backup_schedules', 'backup_mode_policy')
