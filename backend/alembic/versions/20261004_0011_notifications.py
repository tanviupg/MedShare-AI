"""Add in-app notifications."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0011"
down_revision = "20261004_0010"
branch_labels = None
depends_on = None

notification_type = postgresql.ENUM(
    "DONATION_AWAITING_REVIEW", "NEW_MEDICINE_REQUEST", "PRESCRIPTION_AWAITING_VERIFICATION",
    "MEDICINE_EXPIRING_SOON", "MEDICINE_EXPIRED", "WASTE_DISPOSAL_PENDING", "REQUEST_APPROVED",
    "REQUEST_REJECTED", "PRESCRIPTION_APPROVED", "PRESCRIPTION_REJECTED", "READY_FOR_PICKUP",
    "REQUEST_FULFILLED", "DONATION_APPROVED", "DONATION_REJECTED", name="notification_type",
    create_type=False,
)


def upgrade() -> None:
    notification_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", notification_type, nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("related_entity_type", sa.String(40)),
        sa.Column("related_entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("uq_notifications_event_recipient", "notifications", ["recipient_user_id", "type", "related_entity_type", "related_entity_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_notifications_event_recipient", table_name="notifications")
    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
    op.drop_table("notifications")
    notification_type.drop(op.get_bind(), checkfirst=True)
