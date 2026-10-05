"""Store collection handoff reference and disposal notes."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0010"
down_revision = "20261004_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("waste_records", sa.Column("handoff_reference", sa.String(length=120), nullable=True))
    op.add_column("waste_records", sa.Column("disposal_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("waste_records", "disposal_notes")
    op.drop_column("waste_records", "handoff_reference")
