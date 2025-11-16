"""add_application_logs_table

Revision ID: a1b2c3d4e5f6
Revises: 35ddaf609ade
Create Date: 2025-11-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '35ddaf609ade'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create application_logs table for system-wide logging
    op.create_table(
        'application_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('level', sa.String(20), nullable=False),
        sa.Column('logger', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('module', sa.String(255), nullable=True),
        sa.Column('function', sa.String(255), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('pathname', sa.String(500), nullable=True),
        sa.Column('exception', sa.Text(), nullable=True),
        sa.Column('job_id', sa.Integer(), nullable=True),
        sa.Column('backup_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('request_id', sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes for common queries
    op.create_index('ix_application_logs_timestamp', 'application_logs', ['timestamp'])
    op.create_index('ix_application_logs_level', 'application_logs', ['level'])
    op.create_index('ix_application_logs_logger', 'application_logs', ['logger'])
    op.create_index('ix_application_logs_job_id', 'application_logs', ['job_id'])
    op.create_index('ix_application_logs_backup_id', 'application_logs', ['backup_id'])
    op.create_index('ix_application_logs_user_id', 'application_logs', ['user_id'])
    op.create_index('ix_application_logs_request_id', 'application_logs', ['request_id'])

    # Composite indexes for common query patterns
    op.create_index('ix_app_logs_timestamp_level', 'application_logs', ['timestamp', 'level'])
    op.create_index('ix_app_logs_logger_level', 'application_logs', ['logger', 'level'])


def downgrade() -> None:
    # Drop all indexes
    op.drop_index('ix_app_logs_logger_level', table_name='application_logs')
    op.drop_index('ix_app_logs_timestamp_level', table_name='application_logs')
    op.drop_index('ix_application_logs_request_id', table_name='application_logs')
    op.drop_index('ix_application_logs_user_id', table_name='application_logs')
    op.drop_index('ix_application_logs_backup_id', table_name='application_logs')
    op.drop_index('ix_application_logs_job_id', table_name='application_logs')
    op.drop_index('ix_application_logs_logger', table_name='application_logs')
    op.drop_index('ix_application_logs_level', table_name='application_logs')
    op.drop_index('ix_application_logs_timestamp', table_name='application_logs')

    # Drop the table
    op.drop_table('application_logs')
