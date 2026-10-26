from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ACTIVE = ("queued", "running", "retrying")


class Source(Base):
    __tablename__ = "ingestion_source"
    __table_args__ = (UniqueConstraint("source_type", "record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(16))
    record_id: Mapped[int]
    revision: Mapped[int] = mapped_column(default=1)
    content_hash: Mapped[str] = mapped_column(String(64))
    active_job_id: Mapped[int | None]


class IngestionJob(Base):
    __tablename__ = "ingestion_job"
    __table_args__ = (
        Index("ix_ingestion_due", "status", "available_at"),
        Index(
            "uq_ingestion_active_source",
            "source_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'retrying')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_source.id", ondelete="SET NULL"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(16))
    record_id: Mapped[int]
    label: Mapped[str] = mapped_column(String(450))
    revision: Mapped[int]
    trigger: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    stage: Mapped[str] = mapped_column(String(24), default="queued")
    settings: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    plain_text: Mapped[str | None] = mapped_column(Text, deferred=True)
    total_chunks: Mapped[int] = mapped_column(default=0)
    completed_chunks: Mapped[int] = mapped_column(default=0)
    retries: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner: Mapped[str | None] = mapped_column(String(36))


class Chunk(Base):
    __tablename__ = "ingestion_chunk"
    __table_args__ = (UniqueConstraint("job_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_job.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int]
    page_start: Mapped[int | None]
    page_end: Mapped[int | None]
    embedding = mapped_column(Vector(), nullable=True)


class Event(Base):
    __tablename__ = "ingestion_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_job.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    level: Mapped[str] = mapped_column(String(12), default="info")
    message: Mapped[str] = mapped_column(Text)
