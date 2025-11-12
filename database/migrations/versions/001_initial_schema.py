"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2025-11-11 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE userrole AS ENUM ('admin', 'operator', 'viewer')")
    op.execute("CREATE TYPE storagetype AS ENUM ('local', 's3', 'smb', 'nfs')")
    op.execute("CREATE TYPE sourcetype AS ENUM ('vm', 'container')")
    op.execute("CREATE TYPE scheduletype AS ENUM ('daily', 'weekly', 'monthly', 'yearly', 'archive')")
    op.execute("CREATE TYPE backupstatus AS ENUM ('pending', 'running', 'completed', 'failed')")
    op.execute("CREATE TYPE jobtype AS ENUM ('backup', 'restore', 'cleanup', 'sync')")
    op.execute("CREATE TYPE jobstatus AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled')")
    op.execute("CREATE TYPE notificationtype AS ENUM ('email', 'webhook', 'sms')")
    op.execute("CREATE TYPE notificationevent AS ENUM ('backup_success', 'backup_failure', 'backup_start', 'storage_threshold', 'retention_cleanup')")

    # Users table
    op.create_table('users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', postgresql.ENUM('admin', 'operator', 'viewer', name='userrole', create_type=False), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # API Tokens table
    op.create_table('api_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_api_tokens_token_hash'), 'api_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_api_tokens_user_id'), 'api_tokens', ['user_id'])

    # Audit Logs table
    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('details', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'])
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'])

    # Storage Backends table
    op.create_table('storage_backends',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('type', postgresql.ENUM('local', 's3', 'smb', 'nfs', name='storagetype', create_type=False), nullable=False),
        sa.Column('config', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('capacity', sa.Integer(), nullable=True),
        sa.Column('used', sa.Integer(), nullable=True),
        sa.Column('threshold', sa.Integer(), nullable=False, server_default='80'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_storage_backends_name'), 'storage_backends', ['name'], unique=True)
    op.create_index(op.f('ix_storage_backends_type'), 'storage_backends', ['type'])

    # KVM Hosts table
    op.create_table('kvm_hosts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('hostname', sa.String(length=255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False, server_default='22'),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('ssh_key', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_kvm_hosts_hostname'), 'kvm_hosts', ['hostname'])
    op.create_index(op.f('ix_kvm_hosts_name'), 'kvm_hosts', ['name'], unique=True)

    # VMs table
    op.create_table('vms',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('kvm_host_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('state', sa.String(length=50), nullable=True),
        sa.Column('vcpus', sa.Integer(), nullable=True),
        sa.Column('memory', sa.Integer(), nullable=True),
        sa.Column('disk_size', sa.Integer(), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['kvm_host_id'], ['kvm_hosts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vms_kvm_host_id'), 'vms', ['kvm_host_id'])
    op.create_index(op.f('ix_vms_name'), 'vms', ['name'])
    op.create_index(op.f('ix_vms_uuid'), 'vms', ['uuid'], unique=True)

    # Podman Hosts table
    op.create_table('podman_hosts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('hostname', sa.String(length=255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False, server_default='22'),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('ssh_key', sa.Text(), nullable=True),
        sa.Column('socket_path', sa.String(length=500), nullable=False, server_default='/run/podman/podman.sock'),
        sa.Column('config', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_podman_hosts_hostname'), 'podman_hosts', ['hostname'])
    op.create_index(op.f('ix_podman_hosts_name'), 'podman_hosts', ['name'], unique=True)

    # Containers table
    op.create_table('containers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('podman_host_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('container_id', sa.String(length=64), nullable=False),
        sa.Column('image', sa.String(length=255), nullable=True),
        sa.Column('state', sa.String(length=50), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['podman_host_id'], ['podman_hosts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_containers_container_id'), 'containers', ['container_id'], unique=True)
    op.create_index(op.f('ix_containers_name'), 'containers', ['name'])
    op.create_index(op.f('ix_containers_podman_host_id'), 'containers', ['podman_host_id'])

    # Backup Schedules table
    op.create_table('backup_schedules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source_type', postgresql.ENUM('vm', 'container', name='sourcetype', create_type=False), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('schedule_type', postgresql.ENUM('daily', 'weekly', 'monthly', 'yearly', 'archive', name='scheduletype', create_type=False), nullable=False),
        sa.Column('cron_expression', sa.String(length=100), nullable=False),
        sa.Column('retention_config', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('storage_backend_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_run', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['storage_backend_id'], ['storage_backends.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_backup_schedules_name'), 'backup_schedules', ['name'])
    op.create_index(op.f('ix_backup_schedules_schedule_type'), 'backup_schedules', ['schedule_type'])
    op.create_index(op.f('ix_backup_schedules_source_id'), 'backup_schedules', ['source_id'])
    op.create_index(op.f('ix_backup_schedules_source_type'), 'backup_schedules', ['source_type'])

    # Backups table
    op.create_table('backups',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('schedule_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source_type', postgresql.ENUM('vm', 'container', name='sourcetype', create_type=False), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('source_name', sa.String(length=255), nullable=False),
        sa.Column('schedule_type', postgresql.ENUM('daily', 'weekly', 'monthly', 'yearly', 'archive', name='scheduletype', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'running', 'completed', 'failed', name='backupstatus', create_type=False), nullable=False, server_default='pending'),
        sa.Column('size', sa.BigInteger(), nullable=True),
        sa.Column('compressed_size', sa.BigInteger(), nullable=True),
        sa.Column('storage_backend_id', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(length=500), nullable=True),
        sa.Column('checksum', sa.String(length=64), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['schedule_id'], ['backup_schedules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['storage_backend_id'], ['storage_backends.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_backups_expires_at'), 'backups', ['expires_at'])
    op.create_index(op.f('ix_backups_name'), 'backups', ['name'])
    op.create_index(op.f('ix_backups_schedule_id'), 'backups', ['schedule_id'])
    op.create_index(op.f('ix_backups_source_id'), 'backups', ['source_id'])
    op.create_index(op.f('ix_backups_source_name'), 'backups', ['source_name'])
    op.create_index(op.f('ix_backups_status'), 'backups', ['status'])

    # Jobs table
    op.create_table('jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('backup_id', sa.Integer(), nullable=True),
        sa.Column('type', postgresql.ENUM('backup', 'restore', 'cleanup', 'sync', name='jobtype', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'running', 'completed', 'failed', 'cancelled', name='jobstatus', create_type=False), nullable=False, server_default='pending'),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['backup_id'], ['backups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_backup_id'), 'jobs', ['backup_id'])
    op.create_index(op.f('ix_jobs_celery_task_id'), 'jobs', ['celery_task_id'])
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'])
    op.create_index(op.f('ix_jobs_type'), 'jobs', ['type'])

    # Job Logs table
    op.create_table('job_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_logs_job_id'), 'job_logs', ['job_id'])
    op.create_index(op.f('ix_job_logs_level'), 'job_logs', ['level'])

    # Notification Configs table
    op.create_table('notification_configs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', postgresql.ENUM('email', 'webhook', 'sms', name='notificationtype', create_type=False), nullable=False),
        sa.Column('events', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('config', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_configs_user_id'), 'notification_configs', ['user_id'])

    # Notifications table
    op.create_table('notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('event', postgresql.ENUM('backup_success', 'backup_failure', 'backup_start', 'storage_threshold', 'retention_cleanup', name='notificationevent', create_type=False), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_event'), 'notifications', ['event'])
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'])

    # System Settings table
    op.create_table('system_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('value_type', sa.String(length=20), nullable=False, server_default='string'),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_secret', sa.Boolean(), nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_system_settings_category'), 'system_settings', ['category'])
    op.create_index(op.f('ix_system_settings_key'), 'system_settings', ['key'], unique=True)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_system_settings_key'), table_name='system_settings')
    op.drop_index(op.f('ix_system_settings_category'), table_name='system_settings')
    op.drop_table('system_settings')

    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_event'), table_name='notifications')
    op.drop_table('notifications')

    op.drop_index(op.f('ix_notification_configs_user_id'), table_name='notification_configs')
    op.drop_table('notification_configs')

    op.drop_index(op.f('ix_job_logs_level'), table_name='job_logs')
    op.drop_index(op.f('ix_job_logs_job_id'), table_name='job_logs')
    op.drop_table('job_logs')

    op.drop_index(op.f('ix_jobs_type'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_celery_task_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_backup_id'), table_name='jobs')
    op.drop_table('jobs')

    op.drop_index(op.f('ix_backups_status'), table_name='backups')
    op.drop_index(op.f('ix_backups_source_name'), table_name='backups')
    op.drop_index(op.f('ix_backups_source_id'), table_name='backups')
    op.drop_index(op.f('ix_backups_schedule_id'), table_name='backups')
    op.drop_index(op.f('ix_backups_name'), table_name='backups')
    op.drop_index(op.f('ix_backups_expires_at'), table_name='backups')
    op.drop_table('backups')

    op.drop_index(op.f('ix_backup_schedules_source_type'), table_name='backup_schedules')
    op.drop_index(op.f('ix_backup_schedules_source_id'), table_name='backup_schedules')
    op.drop_index(op.f('ix_backup_schedules_schedule_type'), table_name='backup_schedules')
    op.drop_index(op.f('ix_backup_schedules_name'), table_name='backup_schedules')
    op.drop_table('backup_schedules')

    op.drop_index(op.f('ix_containers_podman_host_id'), table_name='containers')
    op.drop_index(op.f('ix_containers_name'), table_name='containers')
    op.drop_index(op.f('ix_containers_container_id'), table_name='containers')
    op.drop_table('containers')

    op.drop_index(op.f('ix_podman_hosts_name'), table_name='podman_hosts')
    op.drop_index(op.f('ix_podman_hosts_hostname'), table_name='podman_hosts')
    op.drop_table('podman_hosts')

    op.drop_index(op.f('ix_vms_uuid'), table_name='vms')
    op.drop_index(op.f('ix_vms_name'), table_name='vms')
    op.drop_index(op.f('ix_vms_kvm_host_id'), table_name='vms')
    op.drop_table('vms')

    op.drop_index(op.f('ix_kvm_hosts_name'), table_name='kvm_hosts')
    op.drop_index(op.f('ix_kvm_hosts_hostname'), table_name='kvm_hosts')
    op.drop_table('kvm_hosts')

    op.drop_index(op.f('ix_storage_backends_type'), table_name='storage_backends')
    op.drop_index(op.f('ix_storage_backends_name'), table_name='storage_backends')
    op.drop_table('storage_backends')

    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')

    op.drop_index(op.f('ix_api_tokens_user_id'), table_name='api_tokens')
    op.drop_index(op.f('ix_api_tokens_token_hash'), table_name='api_tokens')
    op.drop_table('api_tokens')

    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

    # Drop enum types
    op.execute("DROP TYPE notificationevent")
    op.execute("DROP TYPE notificationtype")
    op.execute("DROP TYPE jobstatus")
    op.execute("DROP TYPE jobtype")
    op.execute("DROP TYPE backupstatus")
    op.execute("DROP TYPE scheduletype")
    op.execute("DROP TYPE sourcetype")
    op.execute("DROP TYPE storagetype")
    op.execute("DROP TYPE userrole")
