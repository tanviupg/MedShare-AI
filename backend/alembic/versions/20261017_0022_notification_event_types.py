"""Add notification types for donation submission and clinic review."""
from alembic import op

revision = "20261017_0022"
down_revision = "20261017_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'DONATION_SUBMITTED'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'CLINIC_VERIFICATION_REQUESTED'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values in place.
    pass
