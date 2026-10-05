"""Add auditable pharmacist donation reviews.

Revision ID: 20261004_0003
Revises: 20261004_0002
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0003"
down_revision = "20261004_0002"
branch_labels = None
depends_on = None
review_decision = sa.Enum("APPROVED", "REJECTED", name="donation_review_decision", create_type=False)


def upgrade() -> None:
    review_decision.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "donation_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("donation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pharmacist_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", review_decision, nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["donation_id"], ["donations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pharmacist_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("donation_id", name="uq_donation_reviews_donation_id"),
    )
    op.create_index("ix_donation_reviews_donation_id", "donation_reviews", ["donation_id"])
    op.create_index("ix_donation_reviews_pharmacist_id", "donation_reviews", ["pharmacist_id"])


def downgrade() -> None:
    op.drop_index("ix_donation_reviews_pharmacist_id", table_name="donation_reviews")
    op.drop_index("ix_donation_reviews_donation_id", table_name="donation_reviews")
    op.drop_table("donation_reviews")
    review_decision.drop(op.get_bind(), checkfirst=True)
