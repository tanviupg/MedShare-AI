"""Add request-scoped patient pickup addresses.

Revision ID: 20261005_0018
Revises: 20261005_0017
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0018"
down_revision = "20261005_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("medicine_requests", sa.Column("pickup_address", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("medicine_requests", "pickup_address")
