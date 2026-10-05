"""Reserve inventory when a medicine request is created.

Revision ID: 20261005_0019
Revises: 20261005_0018
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0019"
down_revision = "20261005_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "medicine_requests",
        sa.Column("inventory_reserved", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        "UPDATE medicine_requests SET inventory_reserved = TRUE "
        "WHERE status IN ('APPROVED', 'FULFILLED')"
    )


def downgrade() -> None:
    op.drop_column("medicine_requests", "inventory_reserved")
