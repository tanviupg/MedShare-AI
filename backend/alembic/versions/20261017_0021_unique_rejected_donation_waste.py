"""Allow at most one waste record per rejected donation."""
from alembic import op
import sqlalchemy as sa


revision = "20261017_0021"
down_revision = "20261017_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_waste_records_donation_id",
        "waste_records",
        ["donation_id"],
        unique=True,
        postgresql_where=sa.text("donation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_waste_records_donation_id", table_name="waste_records")
