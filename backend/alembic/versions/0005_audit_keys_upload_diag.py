"""audit_events, api_key lifecycle, upload_diagnostics

Revision ID: 0005_audit_keys_upload_diag
Revises: 0004_signal_history
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_audit_keys_upload_diag"
down_revision = "0004_signal_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("rotation_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("force_rotate", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("api_keys", sa.Column("issued_by", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("revoked_by", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("replaces_key_id", sa.Integer(), nullable=True))

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("actor_label", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("account_id", sa.String(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_target_id", "audit_events", ["target_id"])
    op.create_index("ix_audit_events_account_id", "audit_events", ["account_id"])

    op.create_table(
        "upload_diagnostics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("image_bytes", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
    )
    op.create_index("ix_upload_diagnostics_created_at", "upload_diagnostics", ["created_at"])
    op.create_index("ix_upload_diagnostics_account_id", "upload_diagnostics", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_upload_diagnostics_account_id", table_name="upload_diagnostics")
    op.drop_index("ix_upload_diagnostics_created_at", table_name="upload_diagnostics")
    op.drop_table("upload_diagnostics")
    op.drop_index("ix_audit_events_account_id", table_name="audit_events")
    op.drop_index("ix_audit_events_target_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_column("api_keys", "replaces_key_id")
    op.drop_column("api_keys", "revoked_at")
    op.drop_column("api_keys", "revoked_by")
    op.drop_column("api_keys", "issued_by")
    op.drop_column("api_keys", "force_rotate")
    op.drop_column("api_keys", "rotation_due_at")
    op.drop_column("api_keys", "expires_at")
