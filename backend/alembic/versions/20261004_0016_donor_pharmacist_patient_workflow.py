"""Separate donor logistics, pharmacist verification, and patient-safe classification."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0016"
down_revision = "20261004_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("donations", sa.Column("donor_expiry_date", sa.Date(), nullable=True))
    op.add_column("donations", sa.Column("pickup_address", sa.String(length=500), nullable=True))
    op.execute("UPDATE donations SET donor_expiry_date = expiry_date WHERE donor_expiry_date IS NULL")
    op.add_column("donation_reviews", sa.Column("physical_package_checked", sa.Boolean(), nullable=True))
    op.add_column("donation_reviews", sa.Column("verified_details", sa.JSON(), nullable=True))

    op.add_column(
        "inventory",
        sa.Column("common_use_category", sa.String(length=32), nullable=False, server_default="UNCLASSIFIED"),
    )
    op.add_column(
        "inventory",
        sa.Column("public_id", sa.Uuid(), nullable=True, server_default=sa.text("gen_random_uuid()")),
    )
    op.execute("UPDATE inventory SET public_id = gen_random_uuid() WHERE public_id IS NULL")
    op.alter_column("inventory", "public_id", nullable=False, server_default=sa.text("gen_random_uuid()"))
    op.execute("UPDATE inventory SET prescription_required = TRUE WHERE prescription_required IS DISTINCT FROM TRUE")
    op.alter_column(
        "inventory",
        "prescription_required",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("true"),
    )
    op.create_index("ix_inventory_public_id", "inventory", ["public_id"], unique=True)
    op.create_check_constraint(
        "ck_inventory_common_use_category",
        "inventory",
        "common_use_category IN ('COLD', 'COUGH', 'FLU', 'FEVER', 'PAIN', 'ALLERGY', 'OTHER', 'UNCLASSIFIED')",
    )
    op.create_check_constraint(
        "ck_inventory_category_prescription_rule",
        "inventory",
        "prescription_required = (common_use_category NOT IN ('COLD', 'COUGH', 'FLU', 'FEVER'))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_inventory_category_prescription_rule", "inventory", type_="check")
    op.drop_constraint("ck_inventory_common_use_category", "inventory", type_="check")
    op.drop_index("ix_inventory_public_id", table_name="inventory")
    op.drop_column("inventory", "public_id")
    op.drop_column("inventory", "common_use_category")
    op.alter_column("inventory", "prescription_required", nullable=True, server_default=None)
    op.drop_column("donation_reviews", "verified_details")
    op.drop_column("donation_reviews", "physical_package_checked")
    op.drop_column("donations", "pickup_address")
    op.drop_column("donations", "donor_expiry_date")
