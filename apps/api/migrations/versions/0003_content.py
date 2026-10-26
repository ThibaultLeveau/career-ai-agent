"""Career content and resume PDFs."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def record_columns():
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def timeline_columns():
    return [
        sa.Column("start_month", sa.String(7)),
        sa.Column("end_month", sa.String(7)),
        sa.Column("ongoing", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.CheckConstraint("end_month >= start_month", name="ordered_months"),
        sa.CheckConstraint(
            "NOT ongoing OR end_month IS NULL", name="ongoing_without_end"
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "job",
        *record_columns(),
        *timeline_columns(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("responsibilities", sa.Text(), nullable=False),
        sa.Column("achievements", sa.Text(), nullable=False),
    )
    op.create_table(
        "project",
        *record_columns(),
        *timeline_columns(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("outcomes", sa.Text(), nullable=False),
        sa.Column("website_url", sa.String(2048), nullable=False),
        sa.Column("repository_url", sa.String(2048), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job.id", ondelete="RESTRICT")),
    )
    op.create_index("ix_project_job_id", "project", ["job_id"])
    op.create_table(
        "skill",
        *record_columns(),
        sa.Column("keyword", sa.String(100), nullable=False),
    )
    op.create_index(
        "uq_skill_keyword", "skill", [sa.text("lower(keyword)")], unique=True
    )
    op.create_table(
        "project_skill",
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_id",
            sa.Integer(),
            sa.ForeignKey("skill.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "document",
        *record_columns(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("size > 0 AND size <= 10485760", name="document_size"),
    )


def downgrade() -> None:
    for table in ("document", "project_skill", "skill", "project", "job"):
        op.drop_table(table)
