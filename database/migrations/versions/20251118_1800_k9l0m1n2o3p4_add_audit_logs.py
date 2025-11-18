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
down_revision = 'j8k9l0m1n2o3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # User information
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
            comment='User who performed the action (NULL for system actions)'
        ),
        sa.Column(
            'username',
            sa.String(100),
            nullable=True,
            comment='Username snapshot (preserved even if user deleted)'
        ),

        # Action details
        sa.Column(
            'action',
            sa.String(100),
            nullable=False,
            index=True,
            comment='Action performed (e.g., CREATE_BACKUP, DELETE_VM, LOGIN_SUCCESS)'
        ),
        sa.Column(
            'resource_type',
            sa.String(50),
            nullable=True,
            index=True,
            comment='Type of resource affected (VM, BACKUP, USER, STORAGE, etc.)'
        ),
        sa.Column(
            'resource_id',
            sa.Integer(),
            nullable=True,
            index=True,
            comment='ID of the affected resource'
        ),
        sa.Column(
            'resource_name',
            sa.String(255),
            nullable=True,
            comment='Name snapshot of the affected resource'
        ),

        # Request context
        sa.Column(
            'ip_address',
            sa.String(45),
            nullable=True,
            index=True,
            comment='Client IP address (IPv4 or IPv6)'
        ),
        sa.Column(
            'user_agent',
            sa.Text(),
            nullable=True,
            comment='User agent string from HTTP request'
        ),
        sa.Column(
            'request_method',
            sa.String(10),
            nullable=True,
            comment='HTTP method (GET, POST, PUT, DELETE, etc.)'
        ),
        sa.Column(
            'request_path',
            sa.String(500),
            nullable=True,
            comment='API endpoint path'
        ),
        sa.Column(
            'request_data',
            postgresql.JSONB(),
            nullable=True,
            comment='Sanitized request data (passwords/keys removed)'
        ),

        # Response details
        sa.Column(
            'response_status',
            sa.Integer(),
            nullable=True,
            index=True,
            comment='HTTP response status code'
        ),
        sa.Column(
            'response_message',
            sa.Text(),
            nullable=True,
            comment='Error message or success description'
        ),

        # Metadata
        sa.Column(
            'duration_ms',
            sa.Integer(),
            nullable=True,
            comment='Request duration in milliseconds'
        ),
        sa.Column(
            'severity',
            sa.String(20),
            nullable=False,
            server_default='INFO',
            index=True,
            comment='Log severity: DEBUG, INFO, WARNING, ERROR, CRITICAL'
        ),
        sa.Column(
            'tags',
            postgresql.ARRAY(sa.String(50)),
            nullable=True,
            comment='Searchable tags (e.g., [security, authentication, backup])'
        ),
        sa.Column(
            'metadata',
            postgresql.JSONB(),
            nullable=True,
            comment='Additional contextual information'
        ),

        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for efficient querying
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    op.create_index('idx_audit_logs_user_action', 'audit_logs', ['user_id', 'action'], unique=False)
    op.create_index('idx_audit_logs_resource', 'audit_logs', ['resource_type', 'resource_id'], unique=False)
    op.create_index('idx_audit_logs_severity_created', 'audit_logs', ['severity', 'created_at'], unique=False)

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
    op.drop_index('idx_audit_logs_severity_created', table_name='audit_logs')
    op.drop_index('idx_audit_logs_resource', table_name='audit_logs')
    op.drop_index('idx_audit_logs_user_action', table_name='audit_logs')
    op.drop_index('idx_audit_logs_created_at', table_name='audit_logs')

    # Drop table
    op.drop_table('audit_logs')
