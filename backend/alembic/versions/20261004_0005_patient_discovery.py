"""Add configurable prescription classification for patient discovery.

Revision ID: 20261004_0005
Revises: 20261004_0004
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0005"
down_revision = "20261004_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory", sa.Column("prescription_required", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory", "prescription_required")
