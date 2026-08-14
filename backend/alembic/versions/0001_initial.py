"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("credential_id", sa.String(), primary_key=True),
        sa.Column("broker_name", sa.String(), nullable=False),
        sa.Column("server", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("trading_nonce", sa.String(), nullable=False),
        sa.Column("trading_ciphertext", sa.String(), nullable=False),
        sa.Column("investor_nonce", sa.String(), nullable=True),
        sa.Column("investor_ciphertext", sa.String(), nullable=True),
        sa.Column("execution_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_credentials_account_id", "credentials", ["account_id"])

    op.create_table(
        "subscriptions",
        sa.Column("account_id", sa.String(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("provider_customer_id", sa.String(), nullable=True),
        sa.Column("provider_subscription_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_period_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "processed_payment_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_event_id", sa.String(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_provider_event"),
    )


def downgrade() -> None:
    op.drop_table("processed_payment_events")
    op.drop_table("subscriptions")
    op.drop_index("ix_credentials_account_id", table_name="credentials")
    op.drop_table("credentials")
