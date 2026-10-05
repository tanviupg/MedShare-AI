"""Add authentication users and clinic profiles.

Revision ID: 20261003_0001
Revises:
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261003_0001"
down_revision = None
branch_labels = None
depends_on = None

user_role = sa.Enum("DONOR", "PATIENT", "CLINIC_PHARMACIST", name="user_role", create_type=False)
clinic_status = sa.Enum("PENDING", "VERIFIED", "REJECTED", name="clinic_verification_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    clinic_status.create(bind, checkfirst=True)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("city", sa.String(120)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "clinic_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clinic_name", sa.String(160), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("license_number", sa.String(100)),
        sa.Column("contact_number", sa.String(40)),
        sa.Column("verification_status", clinic_status, server_default="PENDING", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_clinic_profiles_user_id"),
    )


def downgrade() -> None:
    op.drop_table("clinic_profiles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    clinic_status.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
