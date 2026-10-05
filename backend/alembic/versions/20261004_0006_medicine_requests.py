"""Add patient medicine requests and pharmacist reservations.

Revision ID: 20261004_0006
Revises: 20261004_0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0006"
down_revision = "20261004_0005"
branch_labels = None
depends_on = None

request_status = postgresql.ENUM("PENDING", "APPROVED", "REJECTED", "CANCELLED", "FULFILLED", name="medicine_request_status", create_type=False)


def upgrade() -> None:
    request_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "medicine_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inventory.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_quantity", sa.Integer(), nullable=False),
        sa.Column("status", request_status, server_default="PENDING", nullable=False),
        sa.Column("rejection_reason", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("requested_quantity > 0", name="ck_medicine_request_quantity_positive"),
    )
    op.create_index("ix_medicine_requests_patient_id", "medicine_requests", ["patient_id"])
    op.create_index("ix_medicine_requests_inventory_id", "medicine_requests", ["inventory_id"])
    op.create_index("ix_medicine_requests_status", "medicine_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_medicine_requests_status", table_name="medicine_requests")
    op.drop_index("ix_medicine_requests_inventory_id", table_name="medicine_requests")
    op.drop_index("ix_medicine_requests_patient_id", table_name="medicine_requests")
    op.drop_table("medicine_requests")
    request_status.drop(op.get_bind(), checkfirst=True)
