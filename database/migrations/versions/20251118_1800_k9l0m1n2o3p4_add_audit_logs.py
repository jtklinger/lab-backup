"""Add comprehensive audit logging system

Revision ID: k9l0m1n2o3p4
Revises: j8k9l0m1n2o3
Create Date: 2025-11-18 18:00:00.000000

Implements Issue #9 - Enhance audit logging system

Creates audit_logs table for comprehensive security and compliance tracking:
- User actions (who did what, when)
- API requests (method, path, status, duration)
- Resource changes (create, update, delete)
- Authentication events (login, logout, failures)
- Configuration changes (settings, schedules, storage)
- Security events (encryption, key rotation, etc.)

Supports:
- Full audit trail for compliance
- Security event monitoring
- SIEM integration via syslog
- Export for compliance reports
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = 'k9l0m1n2o3p4'
down_revision = 'c9d8e7f6a5b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to existing audit_logs table
    # Note: Table already exists from 001_initial_schema with: id, created_at, updated_at,
    # user_id, action, resource_type, resource_id, details (JSON), ip_address, user_agent

    # Add username for snapshot preservation
    op.add_column('audit_logs', sa.Column(
        'username',
        sa.String(100),
        nullable=True,
        comment='Username snapshot (preserved even if user deleted)'
    ))

    # Add resource name snapshot
    op.add_column('audit_logs', sa.Column(
        'resource_name',
        sa.String(255),
        nullable=True,
        comment='Name snapshot of the affected resource'
    ))

    # Add request context fields
    op.add_column('audit_logs', sa.Column(
        'request_method',
        sa.String(10),
        nullable=True,
        comment='HTTP method (GET, POST, PUT, DELETE, etc.)'
    ))

    op.add_column('audit_logs', sa.Column(
        'request_path',
        sa.String(500),
        nullable=True,
        comment='API endpoint path'
    ))

    op.add_column('audit_logs', sa.Column(
        'request_data',
        postgresql.JSONB(),
        nullable=True,
        comment='Sanitized request data (passwords/keys removed)'
    ))

    # Add response details
    op.add_column('audit_logs', sa.Column(
        'response_status',
        sa.Integer(),
        nullable=True,
        comment='HTTP response status code'
    ))

    op.add_column('audit_logs', sa.Column(
        'response_message',
        sa.Text(),
        nullable=True,
        comment='Error message or success description'
    ))

    # Add metadata fields
    op.add_column('audit_logs', sa.Column(
        'duration_ms',
        sa.Integer(),
        nullable=True,
        comment='Request duration in milliseconds'
    ))

    op.add_column('audit_logs', sa.Column(
        'severity',
        sa.String(20),
        nullable=False,
        server_default='INFO',
        comment='Log severity: DEBUG, INFO, WARNING, ERROR, CRITICAL'
    ))

    op.add_column('audit_logs', sa.Column(
        'tags',
        postgresql.ARRAY(sa.String(50)),
        nullable=True,
        comment='Searchable tags (e.g., [security, authentication, backup])'
    ))

    op.add_column('audit_logs', sa.Column(
        'metadata',
        postgresql.JSONB(),
        nullable=True,
        comment='Additional contextual information'
    ))

    # Update existing ip_address column to support IPv6 (45 chars vs 50)
    op.alter_column('audit_logs', 'ip_address',
                    existing_type=sa.String(50),
                    type_=sa.String(45),
                    comment='Client IP address (IPv4 or IPv6)')

    # Update user_agent to TEXT instead of VARCHAR(255)
    op.alter_column('audit_logs', 'user_agent',
                    existing_type=sa.String(255),
                    type_=sa.Text(),
                    comment='User agent string from HTTP request')

    # Create indexes for efficient querying
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    op.create_index('idx_audit_logs_user_action', 'audit_logs', ['user_id', 'action'], unique=False)
    op.create_index('idx_audit_logs_resource', 'audit_logs', ['resource_type', 'resource_id'], unique=False)
    op.create_index('idx_audit_logs_severity_created', 'audit_logs', ['severity', 'created_at'], unique=False)
    op.create_index('idx_audit_logs_response_status', 'audit_logs', ['response_status'], unique=False)

    # Create GIN index for JSONB columns for fast JSON queries
    op.create_index(
        'idx_audit_logs_request_data_gin',
        'audit_logs',
        ['request_data'],
        unique=False,
        postgresql_using='gin'
    )
    op.create_index(
        'idx_audit_logs_metadata_gin',
        'audit_logs',
        ['metadata'],
        unique=False,
        postgresql_using='gin'
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_audit_logs_metadata_gin', table_name='audit_logs')
    op.drop_index('idx_audit_logs_request_data_gin', table_name='audit_logs')
    op.drop_index('idx_audit_logs_response_status', table_name='audit_logs')
    op.drop_index('idx_audit_logs_severity_created', table_name='audit_logs')
    op.drop_index('idx_audit_logs_resource', table_name='audit_logs')
    op.drop_index('idx_audit_logs_user_action', table_name='audit_logs')
    op.drop_index('idx_audit_logs_created_at', table_name='audit_logs')

    # Revert column type changes
    op.alter_column('audit_logs', 'user_agent',
                    existing_type=sa.Text(),
                    type_=sa.String(255))
    op.alter_column('audit_logs', 'ip_address',
                    existing_type=sa.String(45),
                    type_=sa.String(50))

    # Drop added columns
    op.drop_column('audit_logs', 'metadata')
    op.drop_column('audit_logs', 'tags')
    op.drop_column('audit_logs', 'severity')
    op.drop_column('audit_logs', 'duration_ms')
    op.drop_column('audit_logs', 'response_message')
    op.drop_column('audit_logs', 'response_status')
    op.drop_column('audit_logs', 'request_data')
    op.drop_column('audit_logs', 'request_path')
    op.drop_column('audit_logs', 'request_method')
    op.drop_column('audit_logs', 'resource_name')
    op.drop_column('audit_logs', 'username')
