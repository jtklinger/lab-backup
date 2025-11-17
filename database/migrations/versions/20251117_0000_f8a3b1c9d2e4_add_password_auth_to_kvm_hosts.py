"""add_password_auth_to_kvm_hosts

Revision ID: f8a3b1c9d2e4
Revises: a1b2c3d4e5f6
Create Date: 2025-11-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8a3b1c9d2e4'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add password_encrypted column to kvm_hosts table for SASL/TCP authentication
    op.add_column('kvm_hosts', sa.Column('password_encrypted', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove password_encrypted column
    op.drop_column('kvm_hosts', 'password_encrypted')
