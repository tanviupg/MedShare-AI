"""Add donor donation and image metadata tables.

Revision ID: 20261004_0002
Revises: 20261003_0001
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0002"
down_revision = "20261003_0001"
branch_labels = None
depends_on = None

donation_status = sa.Enum("PENDING_REVIEW", "APPROVED", "REJECTED", "CANCELLED", name="donation_status", create_type=False)


def upgrade() -> None:
    donation_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "donations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("donor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("medicine_name", sa.String(200), nullable=False),
        sa.Column("strength", sa.String(100)),
        sa.Column("dosage_form", sa.String(100)),
        sa.Column("manufacturer", sa.String(200)),
        sa.Column("batch_number", sa.String(100)),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("donor_notes", sa.Text()),
        sa.Column("status", donation_status, server_default="PENDING_REVIEW", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_donations_quantity_positive"),
        sa.ForeignKeyConstraint(["donor_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_donations_donor_id", "donations", ["donor_id"])
    op.create_table(
        "donation_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("donation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name="ck_donation_images_size_positive"),
        sa.ForeignKeyConstraint(["donation_id"], ["donations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("storage_key", name="uq_donation_images_storage_key"),
    )
    op.create_index("ix_donation_images_donation_id", "donation_images", ["donation_id"])


def downgrade() -> None:
    op.drop_index("ix_donation_images_donation_id", table_name="donation_images")
    op.drop_table("donation_images")
    op.drop_index("ix_donations_donor_id", table_name="donations")
    op.drop_table("donations")
    donation_status.drop(op.get_bind(), checkfirst=True)
