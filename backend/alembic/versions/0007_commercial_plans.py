"""commercial plan limits, multi-device bindings, trade counters

Revision ID: 0007_commercial_plans
Revises: 0006_devices_download_plan
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_commercial_plans"
down_revision = "0006_devices_download_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("max_devices", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("max_trades_per_day", sa.Integer(), nullable=False, server_default="10"),
    )

    # Rebuild device_bindings for multi-device (drop old PK-on-account_id shape)
    op.drop_table("device_bindings")
    op.create_table(
        "device_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("device_label", sa.String(), nullable=True),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("account_id", "device_id", name="uq_account_device"),
    )
    op.create_index("ix_device_bindings_account_id", "device_bindings", ["account_id"])
    op.create_index("ix_device_bindings_device_id", "device_bindings", ["device_id"])

    op.create_table(
        "trade_daily_counters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("day", sa.String(), nullable=False),
        sa.Column("trade_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("account_id", "day", name="uq_account_day"),
    )
    op.create_index("ix_trade_daily_counters_account_id", "trade_daily_counters", ["account_id"])


def downgrade() -> None:
    op.drop_table("trade_daily_counters")
    op.drop_table("device_bindings")
    op.create_table(
        "device_bindings",
        sa.Column("account_id", sa.String(), primary_key=True),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("device_label", sa.String(), nullable=True),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_column("subscriptions", "max_trades_per_day")
    op.drop_column("subscriptions", "max_devices")
