"""add_encryption_keys

Revision ID: a1b2c3d4e5f6
Revises: b9c8d7e6f5a4
Create Date: 2025-11-17 23:00:00.000000

Add encryption key management tables to support database-backed key storage.
This enables disaster recovery scenarios where encryption keys can be
exported/imported separately from the database backup.

Key Features:
- Master KEK (Key Encryption Key) remains in .env for security
- DEKs (Data Encryption Keys) stored encrypted in database
- Support for per-storage-backend and per-VM encryption keys
- Key versioning and rotation tracking
- Maintains backward compatibility with global ENCRYPTION_KEY

Related: Issue #7 - Encryption Key Database Storage and Export/Import
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'b9c8d7e6f5a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum for key types
    key_type_enum = postgresql.ENUM(
        'GLOBAL',           # System-wide default encryption key
        'STORAGE_BACKEND',  # Per-storage-backend encryption key
        'VM',              # Per-VM encryption key
        'CONTAINER',       # Per-container encryption key
        name='encryption_key_type',
        create_type=True
    )
    key_type_enum.create(op.get_bind())

    # Create encryption_keys table
    op.create_table(
        'encryption_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key_type', key_type_enum, nullable=False, index=True),
        sa.Column('reference_id', sa.Integer(), nullable=True, index=True,
                  comment='ID of storage_backend/VM/container (NULL for GLOBAL)'),
        sa.Column('encrypted_key', sa.LargeBinary(), nullable=False,
                  comment='DEK encrypted with master KEK from .env'),
        sa.Column('key_version', sa.Integer(), nullable=False, default=1,
                  comment='Increments on rotation'),
        sa.Column('algorithm', sa.String(50), nullable=False, default='Fernet',
                  comment='Encryption algorithm used'),
        sa.Column('active', sa.Boolean(), nullable=False, default=True,
                  comment='Whether this key is currently active'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True,
                  comment='When this key was rotated (replaced)'),
        sa.Column('metadata', sa.JSON(), nullable=True,
                  comment='Additional key metadata'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('idx_encryption_keys_type_ref', 'encryption_keys',
                    ['key_type', 'reference_id'], unique=False)
    op.create_index('idx_encryption_keys_active', 'encryption_keys',
                    ['active'], unique=False)

    # Add encryption fields to backups table
    op.add_column('backups', sa.Column('encryption_key_id', sa.Integer(), nullable=True))
    op.add_column('backups', sa.Column('encryption_scheme', sa.String(20), nullable=True,
                                       server_default='GLOBAL',
                                       comment='GLOBAL, STORAGE, VM, or CONTAINER'))

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_backups_encryption_key_id',
        'backups',
        'encryption_keys',
        ['encryption_key_id'],
        ['id'],
        ondelete='RESTRICT'  # Prevent deleting keys that are in use
    )

    # Create index for querying backups by encryption key
    op.create_index('idx_backups_encryption_key_id', 'backups', ['encryption_key_id'])
    op.create_index('idx_backups_encryption_scheme', 'backups', ['encryption_scheme'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_backups_encryption_scheme', 'backups')
    op.drop_index('idx_backups_encryption_key_id', 'backups')

    # Drop foreign key
    op.drop_constraint('fk_backups_encryption_key_id', 'backups', type_='foreignkey')

    # Drop columns
    op.drop_column('backups', 'encryption_scheme')
    op.drop_column('backups', 'encryption_key_id')

    # Drop indexes
    op.drop_index('idx_encryption_keys_active', 'encryption_keys')
    op.drop_index('idx_encryption_keys_type_ref', 'encryption_keys')

    # Drop table
    op.drop_table('encryption_keys')

    # Drop enum
    encryption_key_type = postgresql.ENUM(name='encryption_key_type')
    encryption_key_type.drop(op.get_bind())
