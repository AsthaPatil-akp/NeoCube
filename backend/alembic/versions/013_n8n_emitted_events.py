"""Persist outbound n8n event_id idempotency

Revision ID: 013_n8n_emitted_events
Revises: 012_product_image_source
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "013_n8n_emitted_events"
down_revision = "012_product_image_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "n8n_emitted_events" in inspector.get_table_names():
        return
    op.create_table(
        "n8n_emitted_events",
        sa.Column("event_id", sa.String(length=160), primary_key=True),
        sa.Column("event_type", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "n8n_emitted_events" in inspector.get_table_names():
        op.drop_table("n8n_emitted_events")
