"""User profile photo filename

Revision ID: 008_profile_photo
Revises: 007_commerce_taxonomy
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "008_profile_photo"
down_revision = "007_commerce_taxonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("profile_photo", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("profile_photo")
