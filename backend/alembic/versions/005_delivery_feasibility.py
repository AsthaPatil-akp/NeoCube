"""Delivery feasibility fields and route estimate cache

Revision ID: 005_delivery_feasibility
Revises: 004_supplier_documents
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "005_delivery_feasibility"
down_revision = "004_supplier_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("matches") as batch:
        batch.add_column(sa.Column("route_distance_km", sa.Float(), nullable=True))
        batch.add_column(sa.Column("estimated_transit_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("estimated_transit_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("estimated_total_delivery_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("supplier_declared_delivery_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("client_requested_delivery_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("delivery_status", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("delivery_warning", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("delivery_estimate_source", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("delivery_estimate_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "route_estimates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("origin_key", sa.String(length=200), nullable=False),
        sa.Column("destination_key", sa.String(length=200), nullable=False),
        sa.Column("origin_text", sa.String(length=200), nullable=False),
        sa.Column("destination_text", sa.String(length=200), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("unavailable_reason", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("origin_key", "destination_key"),
    )


def downgrade() -> None:
    op.drop_table("route_estimates")
    with op.batch_alter_table("matches") as batch:
        batch.drop_column("delivery_estimate_timestamp")
        batch.drop_column("delivery_estimate_source")
        batch.drop_column("delivery_warning")
        batch.drop_column("delivery_status")
        batch.drop_column("client_requested_delivery_days")
        batch.drop_column("supplier_declared_delivery_days")
        batch.drop_column("estimated_total_delivery_days")
        batch.drop_column("estimated_transit_days")
        batch.drop_column("estimated_transit_minutes")
        batch.drop_column("route_distance_km")
