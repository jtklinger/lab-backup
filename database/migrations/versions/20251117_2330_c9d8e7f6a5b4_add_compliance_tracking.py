"""add_compliance_tracking

Revision ID: c9d8e7f6a5b4
Revises: a8b7c6d5e4f3
Create Date: 2025-11-17 23:30:00.000000

Add compliance tracking fields to support enterprise backup compliance monitoring.
Implements HYCU-style state machine (GREY/GREEN/YELLOW/RED) for backup coverage.

Compliance States:
- GREY: No backup policy assigned or VM excluded
- GREEN: Fully compliant (backups within RPO)
- YELLOW: Warning state (backup aging, minor issues)
- RED: Non-compliant (no backups, RPO exceeded)

Related: Issue #8 - Build Compliance Tracking System
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d8e7f6a5b4'
down_revision = 'a8b7c6d5e4f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add compliance tracking to VMs
    op.add_column('vms', sa.Column('compliance_status', sa.String(10), nullable=True,
                                    server_default='GREY',
                                    comment='GREEN/YELLOW/RED/GREY'))
    op.add_column('vms', sa.Column('compliance_reason', sa.Text(), nullable=True,
                                    comment='Human-readable compliance status reason'))
    op.add_column('vms', sa.Column('last_successful_backup', sa.DateTime(timezone=True), nullable=True,
                                    comment='Timestamp of last completed backup'))
    op.add_column('vms', sa.Column('compliance_last_checked', sa.DateTime(timezone=True), nullable=True,
                                    comment='When compliance was last calculated'))

    # Create index for querying by compliance status
    op.create_index('idx_vms_compliance_status', 'vms', ['compliance_status'])
    op.create_index('idx_vms_last_successful_backup', 'vms', ['last_successful_backup'])

    # Add RPO/RTO to backup schedules
    op.add_column('backup_schedules', sa.Column('rpo_minutes', sa.Integer(), nullable=True,
                                                 comment='Recovery Point Objective in minutes'))
    op.add_column('backup_schedules', sa.Column('rto_minutes', sa.Integer(), nullable=True,
                                                 comment='Recovery Time Objective in minutes'))

    # Add compliance tracking to Containers
    op.add_column('containers', sa.Column('compliance_status', sa.String(10), nullable=True,
                                          server_default='GREY',
                                          comment='GREEN/YELLOW/RED/GREY'))
    op.add_column('containers', sa.Column('compliance_reason', sa.Text(), nullable=True,
                                          comment='Human-readable compliance status reason'))
    op.add_column('containers', sa.Column('last_successful_backup', sa.DateTime(timezone=True), nullable=True,
                                          comment='Timestamp of last completed backup'))
    op.add_column('containers', sa.Column('compliance_last_checked', sa.DateTime(timezone=True), nullable=True,
                                          comment='When compliance was last calculated'))

    # Create indexes for containers
    op.create_index('idx_containers_compliance_status', 'containers', ['compliance_status'])
    op.create_index('idx_containers_last_successful_backup', 'containers', ['last_successful_backup'])


def downgrade() -> None:
    # Drop container indexes
    op.drop_index('idx_containers_last_successful_backup', 'containers')
    op.drop_index('idx_containers_compliance_status', 'containers')

    # Drop container columns
    op.drop_column('containers', 'compliance_last_checked')
    op.drop_column('containers', 'last_successful_backup')
    op.drop_column('containers', 'compliance_reason')
    op.drop_column('containers', 'compliance_status')

    # Drop backup schedule columns
    op.drop_column('backup_schedules', 'rto_minutes')
    op.drop_column('backup_schedules', 'rpo_minutes')

    # Drop VM indexes
    op.drop_index('idx_vms_last_successful_backup', 'vms')
    op.drop_index('idx_vms_compliance_status', 'vms')

    # Drop VM columns
    op.drop_column('vms', 'compliance_last_checked')
    op.drop_column('vms', 'last_successful_backup')
    op.drop_column('vms', 'compliance_reason')
    op.drop_column('vms', 'compliance_status')
