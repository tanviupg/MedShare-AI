"""Allow unconfirmed image first donation drafts."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0013"
down_revision = "20261004_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("donations", "medicine_name", existing_type=sa.String(200), nullable=True)
    op.alter_column("donations", "expiry_date", existing_type=sa.Date(), nullable=True)
    op.alter_column("donations", "quantity", existing_type=sa.Integer(), nullable=True)
    op.alter_column("donations", "unit", existing_type=sa.String(40), nullable=True)


def downgrade() -> None:
    op.alter_column("donations", "unit", existing_type=sa.String(40), nullable=False)
    op.alter_column("donations", "quantity", existing_type=sa.Integer(), nullable=False)
    op.alter_column("donations", "expiry_date", existing_type=sa.Date(), nullable=False)
    op.alter_column("donations", "medicine_name", existing_type=sa.String(200), nullable=False)
