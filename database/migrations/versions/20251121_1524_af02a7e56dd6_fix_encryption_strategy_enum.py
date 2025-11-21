"""fix_encryption_strategy_enum

Revision ID: af02a7e56dd6
Revises: j8k9l0m1n2o3
Create Date: 2025-11-21 15:24:31.591512

Fixes the encryption_strategy column in storage_backends table to use a proper PostgreSQL enum type.
The previous migration created it as a VARCHAR, but the model expects a proper enum type.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'af02a7e56dd6'
down_revision = 'j8k9l0m1n2o3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type
    op.execute("""
        CREATE TYPE encryptionstrategy AS ENUM ('DISABLED', 'GLOBAL', 'APP_LEVEL', 'STORAGE_NATIVE')
    """)

    # Convert the column from VARCHAR to enum
    # First, convert existing values to match enum values (just in case)
    op.execute("""
        UPDATE storage_backends
        SET encryption_strategy = UPPER(encryption_strategy)
        WHERE encryption_strategy IS NOT NULL
    """)

    # Drop the default temporarily
    op.execute("""
        ALTER TABLE storage_backends
        ALTER COLUMN encryption_strategy DROP DEFAULT
    """)

    # Alter the column type using USING clause to cast the values
    op.execute("""
        ALTER TABLE storage_backends
        ALTER COLUMN encryption_strategy
        TYPE encryptionstrategy
        USING encryption_strategy::encryptionstrategy
    """)

    # Set the new default using the enum type
    op.execute("""
        ALTER TABLE storage_backends
        ALTER COLUMN encryption_strategy SET DEFAULT 'GLOBAL'::encryptionstrategy
    """)


def downgrade() -> None:
    # Convert back to VARCHAR
    op.execute("""
        ALTER TABLE storage_backends
        ALTER COLUMN encryption_strategy
        TYPE VARCHAR(50)
    """)

    # Drop the enum type
    op.execute("""
        DROP TYPE encryptionstrategy
    """)
