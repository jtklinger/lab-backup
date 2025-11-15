"""add_ssh_keys_table

Revision ID: 35ddaf609ade
Revises: 85559dbd3945
Create Date: 2025-11-15 16:02:31.908685

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '35ddaf609ade'
down_revision = '85559dbd3945'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ssh_keys table for storing SSH keys per KVM host
    op.create_table(
        'ssh_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kvm_host_id', sa.Integer(), nullable=False),
        sa.Column('private_key_encrypted', sa.Text(), nullable=False),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('key_type', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['kvm_host_id'], ['kvm_hosts.id'], ondelete='CASCADE'),
    )

    # Create index on kvm_host_id for faster lookups
    op.create_index('ix_ssh_keys_kvm_host_id', 'ssh_keys', ['kvm_host_id'])


def downgrade() -> None:
    # Drop the table and index
    op.drop_index('ix_ssh_keys_kvm_host_id', table_name='ssh_keys')
    op.drop_table('ssh_keys')
