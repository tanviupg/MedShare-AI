"""Add admin role and clinic verification decision audit fields.

Revision ID: 20261005_0017
Revises: 20261004_0016
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0017"
down_revision = "20261004_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'ADMIN'")
    op.add_column("clinic_profiles", sa.Column("verification_reviewer_id", sa.Uuid(), nullable=True))
    op.add_column("clinic_profiles", sa.Column("verification_decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clinic_profiles", sa.Column("verification_rejection_reason", sa.String(length=1000), nullable=True))
    op.create_foreign_key(
        "fk_clinic_profiles_verification_reviewer_id_users",
        "clinic_profiles",
        "users",
        ["verification_reviewer_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM users WHERE role = 'ADMIN' LIMIT 1")).first():
        raise RuntimeError("Cannot remove ADMIN role while admin accounts exist")
    op.drop_constraint(
        "fk_clinic_profiles_verification_reviewer_id_users",
        "clinic_profiles",
        type_="foreignkey",
    )
    op.drop_column("clinic_profiles", "verification_rejection_reason")
    op.drop_column("clinic_profiles", "verification_decided_at")
    op.drop_column("clinic_profiles", "verification_reviewer_id")
    op.execute("CREATE TYPE user_role_without_admin AS ENUM ('DONOR', 'PATIENT', 'CLINIC_PHARMACIST')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE user_role_without_admin "
        "USING role::text::user_role_without_admin"
    )
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_without_admin RENAME TO user_role")
