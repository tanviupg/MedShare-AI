"""Add auditable waste and disposal records.

Revision ID: 20261004_0009
Revises: 20261004_0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0009"
down_revision = "20261004_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    reason = postgresql.ENUM("EXPIRED", "REJECTED_DONATION", "DAMAGED", name="waste_reason", create_type=False)
    status = postgresql.ENUM("DISPOSAL_PENDING", "COLLECTED", "DISPOSED", name="waste_status", create_type=False)
    reason.create(op.get_bind(), checkfirst=True)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "waste_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inventory_id", sa.Uuid(), nullable=True),
        sa.Column("donation_id", sa.Uuid(), nullable=True),
        sa.Column("pharmacist_id", sa.Uuid(), nullable=False),
        sa.Column("reason", reason, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", status, server_default="DISPOSAL_PENDING", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("disposal_reference", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_by", sa.Uuid(), nullable=True),
        sa.Column("disposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disposed_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_waste_quantity_positive"),
        sa.CheckConstraint("(inventory_id IS NOT NULL AND donation_id IS NULL) OR (inventory_id IS NULL AND donation_id IS NOT NULL)", name="ck_waste_single_source"),
        sa.ForeignKeyConstraint(["inventory_id"], ["inventory.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["donation_id"], ["donations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pharmacist_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["collected_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["disposed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("disposal_reference", name="uq_waste_records_disposal_reference"),
    )
    op.create_index("ix_waste_records_inventory_id", "waste_records", ["inventory_id"])
    op.create_index("ix_waste_records_donation_id", "waste_records", ["donation_id"])
    op.create_index("ix_waste_records_pharmacist_id", "waste_records", ["pharmacist_id"])
    op.create_index("ix_waste_records_disposal_reference", "waste_records", ["disposal_reference"])


def downgrade() -> None:
    op.drop_table("waste_records")
    postgresql.ENUM(name="waste_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="waste_reason").drop(op.get_bind(), checkfirst=True)
