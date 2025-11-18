"""add_backup_verification

Revision ID: b9c8d7e6f5a4
Revises: f8a3b1c9d2e4
Create Date: 2025-11-17 21:45:00.000000

Add backup verification tracking columns to support automated
backup verification via test pod recovery. This enables:
- Tracking verification status per backup
- Storing verification results and metrics
- Linking to verification jobs
- Automated verification scheduling

Related: Issue #6 - Backup Verification Framework
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9c8d7e6f5a4'
down_revision = 'f8a3b1c9d2e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add VERIFICATION to jobtype enum
    op.execute("ALTER TYPE jobtype ADD VALUE IF NOT EXISTS 'verification'")

    # Add verification tracking columns to backups table
    op.add_column('backups', sa.Column('verified', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('backups', sa.Column('verification_date', sa.DateTime(), nullable=True))
    op.add_column('backups', sa.Column('verification_status', sa.String(20), nullable=True))
    op.add_column('backups', sa.Column('verification_error', sa.Text(), nullable=True))
    op.add_column('backups', sa.Column('verification_job_id', sa.Integer(), nullable=True))

    # Add verification metrics columns
    op.add_column('backups', sa.Column('verified_table_count', sa.Integer(), nullable=True))
    op.add_column('backups', sa.Column('verified_size_bytes', sa.BigInteger(), nullable=True))
    op.add_column('backups', sa.Column('verification_duration_seconds', sa.Integer(), nullable=True))

    # Add foreign key constraint to jobs table
    op.create_foreign_key(
        'fk_backups_verification_job_id',
        'backups',
        'jobs',
        ['verification_job_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Create index for querying unverified backups
    op.create_index('idx_backups_verified', 'backups', ['verified'])
    op.create_index('idx_backups_verification_status', 'backups', ['verification_status'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_backups_verification_status', 'backups')
    op.drop_index('idx_backups_verified', 'backups')

    # Drop foreign key
    op.drop_constraint('fk_backups_verification_job_id', 'backups', type_='foreignkey')

    # Drop columns
    op.drop_column('backups', 'verification_duration_seconds')
    op.drop_column('backups', 'verified_size_bytes')
    op.drop_column('backups', 'verified_table_count')
    op.drop_column('backups', 'verification_job_id')
    op.drop_column('backups', 'verification_error')
    op.drop_column('backups', 'verification_status')
    op.drop_column('backups', 'verification_date')
    op.drop_column('backups', 'verified')

    # Note: Cannot remove enum value in PostgreSQL without recreating the type
    # Manual intervention required if downgrade needed
