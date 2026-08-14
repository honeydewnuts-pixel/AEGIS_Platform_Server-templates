"""add portal_token to subscriptions

Revision ID: 0002_portal_token
Revises: 0001_initial
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_portal_token"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("portal_token", sa.String(), nullable=True))
    op.create_unique_constraint("uq_subscriptions_portal_token", "subscriptions", ["portal_token"])


def downgrade() -> None:
    op.drop_constraint("uq_subscriptions_portal_token", "subscriptions", type_="unique")
    op.drop_column("subscriptions", "portal_token")
