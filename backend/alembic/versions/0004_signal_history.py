"""add signal_history table

Revision ID: 0004_signal_history
Revises: 0003_api_keys
Create Date: 2026-08-06
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_signal_history"
down_revision = "0003_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("signal", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rule_name", sa.String(), nullable=False),
        sa.Column("details", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_signal_history_account_id", "signal_history", ["account_id"])
    op.create_index("ix_signal_history_created_at", "signal_history", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_signal_history_created_at", table_name="signal_history")
    op.drop_index("ix_signal_history_account_id", table_name="signal_history")
    op.drop_table("signal_history")
