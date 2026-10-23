"""Administrator access and RAG configuration."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "administrator",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("login_window", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="single_administrator"),
    )
    op.create_table(
        "admin_session",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "administrator_id",
            sa.Integer(),
            sa.ForeignKey("administrator.id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_session_expires_at", "admin_session", ["expires_at"])
    op.create_table(
        "provider_key",
        sa.Column("provider", sa.String(16), primary_key=True),
        sa.Column("encrypted_key", sa.String(), nullable=False),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic')", name="allowed_provider"
        ),
    )
    op.create_table(
        "rag_configuration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.CheckConstraint("id = 1", name="single_configuration"),
    )


def downgrade() -> None:
    for table in (
        "rag_configuration",
        "provider_key",
        "admin_session",
        "administrator",
    ):
        op.drop_table(table)
