"""AI matching tables, RFQ, quotations, match scores

Revision ID: 003_ai_matching
Revises: 002_module2_6
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "003_ai_matching"
down_revision = "002_module2_6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("matches") as batch:
        batch.add_column(sa.Column("semantic_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("ml_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("structured_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("final_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("match_status", sa.String(length=32), nullable=False, server_default="NEW"))
        batch.add_column(sa.Column("explanation", sa.Text(), nullable=True))
        batch.add_column(sa.Column("model_version", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("notification_type", sa.String(length=40), nullable=False, server_default="INFO"))
        batch.add_column(sa.Column("related_type", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("related_id", sa.Integer(), nullable=True))
    op.create_table(
        "rfqs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("client_requirements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offering_id", sa.Integer(), sa.ForeignKey("supplier_offerings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SENT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("requirement_id", "offering_id"),
    )
    op.create_table(
        "quotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("shipping", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tax", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("additional_charges", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("subtotal", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("delivery", sa.String(length=200), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=False),
        sa.Column("payment_terms", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SENT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("quotations")
    op.drop_table("rfqs")
