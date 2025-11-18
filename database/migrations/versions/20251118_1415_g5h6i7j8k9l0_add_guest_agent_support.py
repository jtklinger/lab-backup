"""Add QEMU Guest Agent support for application-consistent backups

Revision ID: g5h6i7j8k9l0
Revises: f4e5d6c7b8a9
Create Date: 2025-11-18 14:15:00.000000

Implements Issue #14 - Integrate QEMU Guest Agent for application consistency

Adds fields to track guest agent availability and enable application-aware backups
with filesystem quiescing and pre/post backup scripts.

Changes to VMs table:
- guest_agent_available: Whether qemu-guest-agent is detected and responsive
- application_consistency_enabled: Whether to attempt app-consistent backups
- pre_backup_script: Optional script to execute before backup (via guest agent)
- post_backup_script: Optional script to execute after backup (via guest agent)
- fsfreeze_timeout_seconds: Timeout for filesystem freeze operations

Changes to backups table:
- application_consistent: Whether this backup was created with app consistency
- fsfreeze_status: Status of filesystem freeze operation
- script_execution_log: Log of pre/post script execution
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'g5h6i7j8k9l0'
down_revision = 'f4e5d6c7b8a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add guest agent tracking to VMs table
    op.add_column('vms', sa.Column(
        'guest_agent_available',
        sa.Boolean(),
        nullable=False,
        server_default='false',
        comment='Whether qemu-guest-agent is detected and responsive'
    ))

    op.add_column('vms', sa.Column(
        'application_consistency_enabled',
        sa.Boolean(),
        nullable=False,
        server_default='true',
        comment='Whether to attempt application-consistent backups (requires guest agent)'
    ))

    op.add_column('vms', sa.Column(
        'pre_backup_script',
        sa.Text(),
        nullable=True,
        comment='Script to execute in guest before backup (e.g., database quiesce)'
    ))

    op.add_column('vms', sa.Column(
        'post_backup_script',
        sa.Text(),
        nullable=True,
        comment='Script to execute in guest after backup (e.g., database resume)'
    ))

    op.add_column('vms', sa.Column(
        'fsfreeze_timeout_seconds',
        sa.Integer(),
        nullable=False,
        server_default='30',
        comment='Timeout for filesystem freeze operations (default 30 seconds)'
    ))

    op.add_column('vms', sa.Column(
        'last_guest_agent_check',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='When guest agent availability was last checked'
    ))

    # Add application consistency tracking to backups table
    op.add_column('backups', sa.Column(
        'application_consistent',
        sa.Boolean(),
        nullable=False,
        server_default='false',
        comment='Whether this backup was created with application consistency (fsfreeze + scripts)'
    ))

    op.add_column('backups', sa.Column(
        'fsfreeze_status',
        sa.String(20),
        nullable=True,
        comment='Status of filesystem freeze: SUCCESS, FAILED, TIMEOUT, NOT_ATTEMPTED'
    ))

    op.add_column('backups', sa.Column(
        'script_execution_log',
        sa.Text(),
        nullable=True,
        comment='Log of pre/post backup script execution results'
    ))

    # Create indexes for guest agent queries
    op.create_index(
        'idx_vms_guest_agent_available',
        'vms',
        ['guest_agent_available'],
        unique=False
    )

    op.create_index(
        'idx_backups_application_consistent',
        'backups',
        ['application_consistent'],
        unique=False
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_backups_application_consistent', table_name='backups')
    op.drop_index('idx_vms_guest_agent_available', table_name='vms')

    # Drop columns from backups table
    op.drop_column('backups', 'script_execution_log')
    op.drop_column('backups', 'fsfreeze_status')
    op.drop_column('backups', 'application_consistent')

    # Drop columns from vms table
    op.drop_column('vms', 'last_guest_agent_check')
    op.drop_column('vms', 'fsfreeze_timeout_seconds')
    op.drop_column('vms', 'post_backup_script')
    op.drop_column('vms', 'pre_backup_script')
    op.drop_column('vms', 'application_consistency_enabled')
    op.drop_column('vms', 'guest_agent_available')
