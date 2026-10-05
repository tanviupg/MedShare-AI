"""Add prescription upload and pharmacist verification.

Revision ID: 20261004_0007
Revises: 20261004_0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0007"
down_revision = "20261004_0006"
branch_labels = None
depends_on = None

prescription_status = postgresql.ENUM("PENDING_REVIEW", "APPROVED", "REJECTED", name="prescription_status", create_type=False)


def upgrade() -> None:
    prescription_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "prescriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicine_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", prescription_status, server_default="PENDING_REVIEW", nullable=False),
        sa.Column("rejection_reason", sa.String(1000)),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prescriptions_request_id", "prescriptions", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_prescriptions_request_id", table_name="prescriptions")
    op.drop_table("prescriptions")
    prescription_status.drop(op.get_bind(), checkfirst=True)
