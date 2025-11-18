"""Add immutable backup support for ransomware protection

Revision ID: i7j8k9l0m1n2
Revises: h6i7j8k9l0m1
Create Date: 2025-11-18 16:00:00.000000

Implements Issue #13 - Implement immutable backup support

Adds support for WORM (Write-Once-Read-Many) immutable backups with:
- Retention enforcement (backups can't be deleted until expiry)
- Multiple retention modes (GOVERNANCE, COMPLIANCE, LEGAL_HOLD)
- S3 Object Lock integration
- Ransomware protection
- Compliance features

Changes to backups table:
- immutable: Whether this backup is write-once-read-many protected
- retention_until: Timestamp when retention expires and deletion is allowed
- retention_mode: Type of retention (GOVERNANCE, COMPLIANCE, LEGAL_HOLD)
- immutability_reason: Human-readable reason for immutability

Creates database trigger to prevent deletion of immutable backups.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = 'i7j8k9l0m1n2'
down_revision = 'h6i7j8k9l0m1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add immutability fields to backups table
    op.add_column('backups', sa.Column(
        'immutable',
        sa.Boolean(),
        nullable=False,
        server_default='false',
        comment='Whether this backup is immutable (WORM protected)'
    ))

    op.add_column('backups', sa.Column(
        'retention_until',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='Timestamp when retention expires and deletion is allowed'
    ))

    op.add_column('backups', sa.Column(
        'retention_mode',
        sa.String(20),
        nullable=True,
        comment='Retention mode: GOVERNANCE, COMPLIANCE, LEGAL_HOLD'
    ))

    op.add_column('backups', sa.Column(
        'immutability_reason',
        sa.String(255),
        nullable=True,
        comment='Human-readable reason for immutability (compliance, ransomware protection, etc.)'
    ))

    # Create indexes for immutable backup queries
    op.create_index(
        'idx_backups_immutable',
        'backups',
        ['immutable'],
        unique=False
    )

    op.create_index(
        'idx_backups_retention_until',
        'backups',
        ['retention_until'],
        unique=False
    )

    # Create function to prevent deletion of immutable backups
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_immutable_backup_deletion()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Check if backup is immutable and still under retention
            IF OLD.immutable = true THEN
                -- COMPLIANCE mode: Always block deletion until retention expires
                IF OLD.retention_mode = 'COMPLIANCE' AND (OLD.retention_until IS NULL OR OLD.retention_until > NOW()) THEN
                    RAISE EXCEPTION 'Cannot delete immutable backup (ID: %) in COMPLIANCE mode. Retention until: %',
                        OLD.id,
                        COALESCE(OLD.retention_until::TEXT, 'indefinite');
                END IF;

                -- LEGAL_HOLD mode: Block deletion indefinitely
                IF OLD.retention_mode = 'LEGAL_HOLD' THEN
                    RAISE EXCEPTION 'Cannot delete backup (ID: %) under LEGAL_HOLD. Legal hold must be removed first.',
                        OLD.id;
                END IF;

                -- GOVERNANCE mode: Log warning but allow deletion
                -- (Admin override assumed - actual permission check done in application layer)
                IF OLD.retention_mode = 'GOVERNANCE' AND (OLD.retention_until IS NULL OR OLD.retention_until > NOW()) THEN
                    RAISE WARNING 'Deleting immutable backup (ID: %) in GOVERNANCE mode before retention expires. Admin override required.',
                        OLD.id;
                END IF;
            END IF;

            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger to check immutability before deletion
    op.execute("""
        CREATE TRIGGER check_immutable_backup_deletion
            BEFORE DELETE ON backups
            FOR EACH ROW
            EXECUTE FUNCTION prevent_immutable_backup_deletion();
    """)


def downgrade() -> None:
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS check_immutable_backup_deletion ON backups;")
    op.execute("DROP FUNCTION IF EXISTS prevent_immutable_backup_deletion();")

    # Drop indexes
    op.drop_index('idx_backups_retention_until', table_name='backups')
    op.drop_index('idx_backups_immutable', table_name='backups')

    # Drop columns
    op.drop_column('backups', 'immutability_reason')
    op.drop_column('backups', 'retention_mode')
    op.drop_column('backups', 'retention_until')
    op.drop_column('backups', 'immutable')
