"""device bindings, download tokens, subscription plan

Revision ID: 0006_devices_download_plan
Revises: 0005_audit_keys_upload_diag
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_devices_download_plan"
down_revision = "0005_audit_keys_upload_diag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("plan", sa.String(), nullable=False, server_default="live"),
    )
    op.create_table(
        "device_bindings",
        sa.Column("account_id", sa.String(), primary_key=True),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("device_label", sa.String(), nullable=True),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_device_bindings_device_id", "device_bindings", ["device_id"])

    op.create_table(
        "download_tokens",
        sa.Column("token", sa.String(), primary_key=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("plan", sa.String(), nullable=False, server_default="live"),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_download_tokens_account_id", "download_tokens", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_download_tokens_account_id", table_name="download_tokens")
    op.drop_table("download_tokens")
    op.drop_index("ix_device_bindings_device_id", table_name="device_bindings")
    op.drop_table("device_bindings")
    op.drop_column("subscriptions", "plan")
