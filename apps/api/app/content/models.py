from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

project_skill = Table(
    "project_skill",
    Base.metadata,
    Column(
        "project_id", ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("skill_id", ForeignKey("skill.id", ondelete="CASCADE"), primary_key=True),
)


class Record:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def ingestion(self):
        from sqlalchemy.orm import object_session

        from app.ingestion.service import MODELS, summary

        source_type = next(
            key for key, model in MODELS.items() if isinstance(self, model)
        )
        return summary(object_session(self), source_type, self.id)


class Timeline:
    start_month: Mapped[str | None] = mapped_column(String(7))
    end_month: Mapped[str | None] = mapped_column(String(7))
    ongoing: Mapped[bool] = mapped_column(default=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    small_summary: Mapped[str] = mapped_column(
        String(280), default="", server_default=""
    )


def timeline_constraints():
    return (
        CheckConstraint("end_month >= start_month", name="ordered_months"),
        CheckConstraint("NOT ongoing OR end_month IS NULL", name="ongoing_without_end"),
    )


class Job(Record, Timeline, Base):
    __tablename__ = "job"
    __table_args__ = timeline_constraints()

    title: Mapped[str] = mapped_column(String(200))
    company: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200), default="")
    responsibilities: Mapped[str] = mapped_column(Text, default="")
    achievements: Mapped[str] = mapped_column(Text, default="")
    projects: Mapped[list[Project]] = relationship(
        back_populates="job", passive_deletes="all", lazy="selectin"
    )

    @property
    def project_count(self) -> int:
        return len(self.projects)


class Project(Record, Timeline, Base):
    __tablename__ = "project"
    __table_args__ = timeline_constraints()

    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    contribution: Mapped[str] = mapped_column(Text, default="", server_default="")
    outcomes: Mapped[str] = mapped_column(Text, default="")
    website_url: Mapped[str] = mapped_column(String(2048), default="")
    repository_url: Mapped[str] = mapped_column(String(2048), default="")
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("job.id", ondelete="RESTRICT"), index=True
    )
    job: Mapped[Job | None] = relationship(back_populates="projects")
    skills: Mapped[list[Skill]] = relationship(
        secondary=project_skill, lazy="selectin", order_by="Skill.keyword"
    )

    @property
    def kind(self) -> str:
        return "professional" if self.job_id is not None else "personal"


class Skill(Record, Base):
    __tablename__ = "skill"

    keyword: Mapped[str] = mapped_column(String(100))
    __table_args__ = (Index("uq_skill_keyword", func.lower(keyword), unique=True),)


class Document(Record, Base):
    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint("size > 0 AND size <= 10485760", name="document_size"),
    )

    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int]
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
