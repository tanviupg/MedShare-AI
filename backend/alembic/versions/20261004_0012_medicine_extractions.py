"""Add persistent medicine image extraction records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0012"
down_revision = "20261004_0011"
branch_labels = None
depends_on = None

extraction_status = postgresql.ENUM("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="extraction_status", create_type=False)


def upgrade() -> None:
    op.add_column("donations", sa.Column("details_confirmed", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("donations", sa.Column("packaging_type", sa.String(100), nullable=True))
    extraction_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "medicine_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("donation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("donations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("donation_images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", extraction_status, nullable=False),
        sa.Column("extracted_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_name", sa.String(80), nullable=False),
        sa.Column("provider_version", sa.String(80)),
        sa.Column("error_message", sa.String(240)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_medicine_extractions_donation_id", "medicine_extractions", ["donation_id"])
    op.create_index("ix_medicine_extractions_image_id", "medicine_extractions", ["image_id"])


def downgrade() -> None:
    op.drop_index("ix_medicine_extractions_image_id", table_name="medicine_extractions")
    op.drop_index("ix_medicine_extractions_donation_id", table_name="medicine_extractions")
    op.drop_table("medicine_extractions")
    extraction_status.drop(op.get_bind(), checkfirst=True)
    op.drop_column("donations", "details_confirmed")
    op.drop_column("donations", "packaging_type")
