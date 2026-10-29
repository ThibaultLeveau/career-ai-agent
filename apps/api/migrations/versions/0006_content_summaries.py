"""Project contributions and compact list summaries."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("job", "project"):
        op.add_column(
            table,
            sa.Column(
                "small_summary", sa.String(280), nullable=False, server_default=""
            ),
        )
    op.add_column(
        "project",
        sa.Column("contribution", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("project", "contribution")
    for table in ("project", "job"):
        op.drop_column(table, "small_summary")
