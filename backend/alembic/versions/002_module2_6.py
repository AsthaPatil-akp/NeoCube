"""module 2-6 matchmaking tables

Revision ID: 002_module2_6
Revises: 001_module1
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "002_module2_6"
down_revision = "001_module1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "client_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("product_requirement", sa.String(length=300), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("budget", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("delivery_timeline", sa.String(length=100), nullable=False),
        sa.Column("additional_notes", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_client_requirements_client_id", "client_requirements", ["client_id"])
    op.create_index("ix_client_requirements_category_id", "client_requirements", ["category_id"])
    op.create_index("ix_client_requirements_status", "client_requirements", ["status"])
    op.create_table(
        "supplier_offerings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("supplier_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("supplier_name", sa.String(length=200), nullable=False),
        sa.Column("product_offered", sa.String(length=300), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("pricing_details", sa.String(length=300), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("delivery_capability", sa.String(length=200), nullable=False),
        sa.Column("additional_notes", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_supplier_offerings_supplier_id", "supplier_offerings", ["supplier_id"])
    op.create_index("ix_supplier_offerings_category_id", "supplier_offerings", ["category_id"])
    op.create_index("ix_supplier_offerings_status", "supplier_offerings", ["status"])
    op.create_table(
        "requirement_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("client_requirements.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("extracted_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_requirement_documents_user_id", "requirement_documents", ["user_id"])
    op.create_index("ix_requirement_documents_requirement_id", "requirement_documents", ["requirement_id"])
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("client_requirements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offering_id", sa.Integer(), sa.ForeignKey("supplier_offerings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("requirement_id", "offering_id"),
    )
    op.create_index("ix_matches_requirement_id", "matches", ["requirement_id"])
    op.create_index("ix_matches_offering_id", "matches", ["offering_id"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_matches_offering_id", table_name="matches")
    op.drop_index("ix_matches_requirement_id", table_name="matches")
    op.drop_table("matches")
    op.drop_index("ix_requirement_documents_requirement_id", table_name="requirement_documents")
    op.drop_index("ix_requirement_documents_user_id", table_name="requirement_documents")
    op.drop_table("requirement_documents")
    op.drop_index("ix_supplier_offerings_status", table_name="supplier_offerings")
    op.drop_index("ix_supplier_offerings_category_id", table_name="supplier_offerings")
    op.drop_index("ix_supplier_offerings_supplier_id", table_name="supplier_offerings")
    op.drop_table("supplier_offerings")
    op.drop_index("ix_client_requirements_status", table_name="client_requirements")
    op.drop_index("ix_client_requirements_category_id", table_name="client_requirements")
    op.drop_index("ix_client_requirements_client_id", table_name="client_requirements")
    op.drop_table("client_requirements")
    op.drop_table("categories")
