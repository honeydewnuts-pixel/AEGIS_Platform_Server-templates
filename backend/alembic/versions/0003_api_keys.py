"""add api_keys table for per-account authorization

Revision ID: 0003_api_keys
Revises: 0002_portal_token
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_api_keys"
down_revision = "0002_portal_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key_hash", sa.String(), nullable=False, unique=True),
        sa.Column("account_id", sa.String(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)
    op.create_index("ix_api_keys_account_id", "api_keys", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_account_id", table_name="api_keys")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
