"""Supplier catalog documents (Alembic 004)

Revision ID: 004_supplier_documents
Revises: 003_ai_matching
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "004_supplier_documents"
down_revision = "003_ai_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offering_id", sa.Integer(), sa.ForeignKey("supplier_offerings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("extracted_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_supplier_documents_user_id", "supplier_documents", ["user_id"])
    op.create_index("ix_supplier_documents_offering_id", "supplier_documents", ["offering_id"])


def downgrade() -> None:
    op.drop_index("ix_supplier_documents_offering_id", table_name="supplier_documents")
    op.drop_index("ix_supplier_documents_user_id", table_name="supplier_documents")
    op.drop_table("supplier_documents")
