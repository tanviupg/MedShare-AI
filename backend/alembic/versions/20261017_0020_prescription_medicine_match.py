"""Store conservative prescription extraction for pharmacist review."""
from alembic import op
import sqlalchemy as sa

revision = "20261017_0020"
down_revision = "20261005_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prescriptions", sa.Column("extracted_medicine_name", sa.String(200), nullable=True))
    op.add_column("prescriptions", sa.Column("extracted_strength", sa.String(100), nullable=True))
    op.add_column("prescriptions", sa.Column("extracted_dosage_form", sa.String(100), nullable=True))
    op.add_column("prescriptions", sa.Column("extraction_confidence", sa.Float(), nullable=True))
    op.add_column("prescriptions", sa.Column("medicine_match", sa.String(10), server_default="UNCERTAIN", nullable=False))


def downgrade() -> None:
    op.drop_column("prescriptions", "medicine_match")
    op.drop_column("prescriptions", "extraction_confidence")
    op.drop_column("prescriptions", "extracted_dosage_form")
    op.drop_column("prescriptions", "extracted_strength")
    op.drop_column("prescriptions", "extracted_medicine_name")
