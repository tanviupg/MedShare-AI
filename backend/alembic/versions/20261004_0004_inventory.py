"""Create traceable clinic inventory from approved donations.

Revision ID: 20261004_0004
Revises: 20261004_0003
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0004"
down_revision = "20261004_0003"
branch_labels = None
depends_on = None

inventory_status = postgresql.ENUM("AVAILABLE", "RESERVED", "EXPIRED", "DEPLETED", "REMOVED", name="inventory_status", create_type=False)


def upgrade() -> None:
    inventory_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("donation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pharmacist_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("medicine_name", sa.String(200), nullable=False),
        sa.Column("strength", sa.String(100)),
        sa.Column("dosage_form", sa.String(100)),
        sa.Column("manufacturer", sa.String(200)),
        sa.Column("batch_number", sa.String(100)),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("quantity_available", sa.Integer(), nullable=False),
        sa.Column("original_quantity", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("status", inventory_status, server_default="AVAILABLE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity_available >= 0", name="ck_inventory_quantity_nonnegative"),
        sa.CheckConstraint("original_quantity > 0", name="ck_inventory_original_quantity_positive"),
        sa.CheckConstraint("quantity_available <= original_quantity", name="ck_inventory_quantity_lte_original"),
        sa.CheckConstraint("(quantity_available = 0 AND status = 'DEPLETED') OR (quantity_available > 0 AND status <> 'DEPLETED')", name="ck_inventory_zero_quantity_depleted"),
        sa.ForeignKeyConstraint(["donation_id"], ["donations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pharmacist_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("donation_id", name="uq_inventory_donation_id"),
    )
    op.create_index("ix_inventory_donation_id", "inventory", ["donation_id"])
    op.create_index("ix_inventory_pharmacist_id", "inventory", ["pharmacist_id"])


def downgrade() -> None:
    op.drop_index("ix_inventory_pharmacist_id", table_name="inventory")
    op.drop_index("ix_inventory_donation_id", table_name="inventory")
    op.drop_table("inventory")
    inventory_status.drop(op.get_bind(), checkfirst=True)
