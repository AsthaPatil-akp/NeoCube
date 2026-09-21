"""Order tracking lifecycle for accepted RFQs

Revision ID: 009_order_tracks
Revises: 008_profile_photo
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "009_order_tracks"
down_revision = "008_profile_photo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_tracks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_status", sa.String(length=32), nullable=False, server_default="ACCEPTED"),
        sa.Column("payment_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("shipment_status", sa.String(length=32), nullable=False, server_default="NOT_SHIPPED"),
        sa.Column("received_status", sa.String(length=32), nullable=False, server_default="NOT_RECEIVED"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipment_code", sa.String(length=40), nullable=True),
        sa.Column("otp_hash", sa.String(length=128), nullable=True),
        sa.Column("otp_code", sa.String(length=6), nullable=True),
        sa.Column("otp_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rfq_id"),
    )


def downgrade() -> None:
    op.drop_table("order_tracks")
