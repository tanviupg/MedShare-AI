"""Add request pickup codes and dispensing audit records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0008"
down_revision = "20261004_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("medicine_requests", sa.Column("pickup_code", sa.String(9), nullable=True))
    op.create_index("ix_medicine_requests_pickup_code", "medicine_requests", ["pickup_code"], unique=True)
    op.create_table(
        "dispensing_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicine_requests.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inventory.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pharmacist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity_dispensed", sa.Integer(), nullable=False),
        sa.Column("dispensed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity_dispensed > 0", name="ck_dispensing_quantity_positive"),
    )
    op.create_index("ix_dispensing_records_request_id", "dispensing_records", ["request_id"], unique=True)
    op.create_index("ix_dispensing_records_inventory_id", "dispensing_records", ["inventory_id"])
    op.create_index("ix_dispensing_records_pharmacist_id", "dispensing_records", ["pharmacist_id"])


def downgrade() -> None:
    op.drop_index("ix_dispensing_records_pharmacist_id", table_name="dispensing_records")
    op.drop_index("ix_dispensing_records_inventory_id", table_name="dispensing_records")
    op.drop_index("ix_dispensing_records_request_id", table_name="dispensing_records")
    op.drop_table("dispensing_records")
    op.drop_index("ix_medicine_requests_pickup_code", table_name="medicine_requests")
    op.drop_column("medicine_requests", "pickup_code")
