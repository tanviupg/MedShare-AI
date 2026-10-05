"""Repair the donation packaging column if a database was stamped ahead."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0015"
down_revision = "20261004_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("donations")}
    if "packaging_type" not in columns:
        op.add_column("donations", sa.Column("packaging_type", sa.String(100), nullable=True))


def downgrade() -> None:
    # The column predates this repair and is required by the current model.
    pass
