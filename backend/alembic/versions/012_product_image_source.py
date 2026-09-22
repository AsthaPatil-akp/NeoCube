"""Add product_image_source to supplier offerings

Revision ID: 012_product_image_source
Revises: 011_product_vision
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "012_product_image_source"
down_revision = "011_product_vision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("supplier_offerings")}
    if "product_image_source" not in existing:
        op.add_column(
            "supplier_offerings",
            sa.Column("product_image_source", sa.String(length=40), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("supplier_offerings")}
    if "product_image_source" in existing:
        op.drop_column("supplier_offerings", "product_image_source")
