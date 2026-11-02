"""Document categories and explicitly enabled chat resumes."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    document_type = op.create_table(
        "document_type",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index(
        "uq_document_type_name", "document_type", [sa.text("lower(name)")], unique=True
    )
    op.bulk_insert(
        document_type,
        [
            {"key": "resume", "name": "Resume", "is_builtin": True},
            {"key": "other", "name": "Other", "is_builtin": True},
        ],
    )
    op.add_column(
        "document",
        sa.Column(
            "document_type_key", sa.String(100), nullable=False, server_default="other"
        ),
    )
    op.create_foreign_key(
        "fk_document_document_type_key",
        "document",
        "document_type",
        ["document_type_key"],
        ["key"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_document_document_type_key", "document", ["document_type_key"])
    op.add_column(
        "document",
        sa.Column(
            "available_in_chat", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "document",
        sa.Column("matching_notes", sa.String(2000), nullable=False, server_default=""),
    )
    op.create_check_constraint(
        "document_chat_resume_only",
        "document",
        "NOT available_in_chat OR document_type_key = 'resume'",
    )


def downgrade() -> None:
    op.drop_constraint("document_chat_resume_only", "document", type_="check")
    op.drop_column("document", "matching_notes")
    op.drop_column("document", "available_in_chat")
    op.drop_index("ix_document_document_type_key", table_name="document")
    op.drop_constraint("fk_document_document_type_key", "document", type_="foreignkey")
    op.drop_column("document", "document_type_key")
    op.drop_table("document_type")
