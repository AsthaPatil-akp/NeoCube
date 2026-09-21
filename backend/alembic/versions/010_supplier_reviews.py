"""Supplier reviews tied to completed RFQs

Revision ID: 010_supplier_reviews
Revises: 009_order_tracks
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "010_supplier_reviews"
down_revision = "009_order_tracks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "supplier_id",
            sa.Integer(),
            sa.ForeignKey("supplier_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("feedback", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rfq_id"),
    )
    op.create_index("ix_supplier_reviews_supplier_id", "supplier_reviews", ["supplier_id"])
    op.create_index("ix_supplier_reviews_client_user_id", "supplier_reviews", ["client_user_id"])


def downgrade() -> None:
    op.drop_index("ix_supplier_reviews_client_user_id", table_name="supplier_reviews")
    op.drop_index("ix_supplier_reviews_supplier_id", table_name="supplier_reviews")
    op.drop_table("supplier_reviews")
