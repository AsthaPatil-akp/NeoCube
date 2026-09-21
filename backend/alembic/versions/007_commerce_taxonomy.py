"""Structured category, budget, and supplier pricing fields

Revision ID: 007_commerce_taxonomy
Revises: 006_remove_google_routes
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "007_commerce_taxonomy"
down_revision = "006_remove_google_routes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.add_column(
            sa.Column("is_predefined", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.alter_column(
            "name",
            existing_type=sa.String(length=100),
            type_=sa.String(length=200),
            existing_nullable=False,
        )
    with op.batch_alter_table("client_requirements") as batch:
        batch.add_column(sa.Column("custom_category", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("quantity_unit", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("budget_currency", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("budget_basis", sa.String(length=16), nullable=True))
    with op.batch_alter_table("supplier_offerings") as batch:
        batch.add_column(sa.Column("custom_category", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("quantity_unit", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("price_amount", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("price_currency", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("price_basis", sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("supplier_offerings") as batch:
        batch.drop_column("price_basis")
        batch.drop_column("price_currency")
        batch.drop_column("price_amount")
        batch.drop_column("quantity_unit")
        batch.drop_column("custom_category")
    with op.batch_alter_table("client_requirements") as batch:
        batch.drop_column("budget_basis")
        batch.drop_column("budget_currency")
        batch.drop_column("quantity_unit")
        batch.drop_column("custom_category")
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("is_predefined")
        batch.alter_column(
            "name",
            existing_type=sa.String(length=200),
            type_=sa.String(length=100),
            existing_nullable=False,
        )
