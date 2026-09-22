"""Optional product images and vision embeddings for AI Product Finder

Revision ID: 011_product_vision
Revises: 010_supplier_reviews
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "011_product_vision"
down_revision = "010_supplier_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplier_offerings", sa.Column("product_image_path", sa.String(length=255), nullable=True))
    op.add_column("supplier_offerings", sa.Column("product_image_filename", sa.String(length=255), nullable=True))
    op.add_column("supplier_offerings", sa.Column("product_image_mime_type", sa.String(length=80), nullable=True))
    op.create_table(
        "product_image_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "supplier_offering_id",
            sa.Integer(),
            sa.ForeignKey("supplier_offerings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("supplier_offering_id"),
    )
    op.create_index(
        "ix_product_image_embeddings_supplier_offering_id",
        "product_image_embeddings",
        ["supplier_offering_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_image_embeddings_supplier_offering_id", table_name="product_image_embeddings")
    op.drop_table("product_image_embeddings")
    op.drop_column("supplier_offerings", "product_image_mime_type")
    op.drop_column("supplier_offerings", "product_image_filename")
    op.drop_column("supplier_offerings", "product_image_path")
