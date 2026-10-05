"""Add configurable inventory pricing and simulated checkout records."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0014"
down_revision = "20261004_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory", sa.Column("original_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("inventory", sa.Column("discount_percentage", sa.Numeric(5, 2), nullable=True))
    op.add_column("inventory", sa.Column("patient_price", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint("ck_inventory_original_price_nonnegative", "inventory", "original_price IS NULL OR original_price >= 0")
    op.create_check_constraint("ck_inventory_discount_range", "inventory", "discount_percentage IS NULL OR (discount_percentage >= 0 AND discount_percentage <= 100)")
    op.create_check_constraint("ck_inventory_patient_price_nonnegative", "inventory", "patient_price IS NULL OR patient_price >= 0")
    op.add_column("medicine_requests", sa.Column("price_original_snapshot", sa.Numeric(12, 2), nullable=True))
    op.add_column("medicine_requests", sa.Column("discount_snapshot", sa.Numeric(5, 2), nullable=True))
    op.add_column("medicine_requests", sa.Column("patient_price_snapshot", sa.Numeric(12, 2), nullable=True))
    op.create_table(
        "checkouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("patient_user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("payment_status", sa.Enum("PENDING", "PAID", "FAILED", "CANCELLED", name="payment_status"), server_default="PENDING", nullable=False),
        sa.Column("payment_method", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_checkouts_amount_nonnegative"),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["request_id"], ["medicine_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_checkouts_request_id", "checkouts", ["request_id"], unique=True)
    op.create_index("ix_checkouts_patient_user_id", "checkouts", ["patient_user_id"])


def downgrade() -> None:
    op.drop_index("ix_checkouts_patient_user_id", table_name="checkouts")
    op.drop_index("ix_checkouts_request_id", table_name="checkouts")
    op.drop_table("checkouts")
    op.drop_column("medicine_requests", "patient_price_snapshot")
    op.drop_column("medicine_requests", "discount_snapshot")
    op.drop_column("medicine_requests", "price_original_snapshot")
    op.drop_constraint("ck_inventory_patient_price_nonnegative", "inventory", type_="check")
    op.drop_constraint("ck_inventory_discount_range", "inventory", type_="check")
    op.drop_constraint("ck_inventory_original_price_nonnegative", "inventory", type_="check")
    op.drop_column("inventory", "patient_price")
    op.drop_column("inventory", "discount_percentage")
    op.drop_column("inventory", "original_price")
    op.execute("DROP TYPE payment_status")
