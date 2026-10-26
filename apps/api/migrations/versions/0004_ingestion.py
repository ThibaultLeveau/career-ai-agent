"""Durable ingestion queue, logs, text, and vectors."""

import json

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE ingestion_source (
            id SERIAL PRIMARY KEY, source_type VARCHAR(16) NOT NULL,
            record_id INTEGER NOT NULL, revision INTEGER NOT NULL,
            content_hash VARCHAR(64) NOT NULL, active_job_id INTEGER,
            UNIQUE (source_type, record_id)
        );
        CREATE TABLE ingestion_job (
            id SERIAL PRIMARY KEY,
            source_id INTEGER REFERENCES ingestion_source(id) ON DELETE SET NULL,
            source_type VARCHAR(16) NOT NULL, record_id INTEGER NOT NULL,
            label VARCHAR(450) NOT NULL, revision INTEGER NOT NULL,
            trigger VARCHAR(24) NOT NULL, status VARCHAR(16) NOT NULL,
            stage VARCHAR(24) NOT NULL, settings JSON NOT NULL,
            fingerprint VARCHAR(64) NOT NULL, plain_text TEXT,
            total_chunks INTEGER NOT NULL, completed_chunks INTEGER NOT NULL,
            retries INTEGER NOT NULL, error TEXT, created_at TIMESTAMPTZ NOT NULL,
            started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL, lease_until TIMESTAMPTZ,
            owner VARCHAR(36)
        );
        CREATE INDEX ix_ingestion_job_source_id ON ingestion_job(source_id);
        CREATE INDEX ix_ingestion_due ON ingestion_job(status, available_at);
        CREATE UNIQUE INDEX uq_ingestion_active_source ON ingestion_job(source_id)
            WHERE status IN ('queued', 'running', 'retrying');
        CREATE TABLE ingestion_chunk (
            id SERIAL PRIMARY KEY,
            job_id INTEGER NOT NULL REFERENCES ingestion_job(id) ON DELETE CASCADE,
            position INTEGER NOT NULL, text TEXT NOT NULL,
            token_count INTEGER NOT NULL, page_start INTEGER, page_end INTEGER,
            embedding vector, UNIQUE (job_id, position)
        );
        CREATE INDEX ix_ingestion_chunk_job_id ON ingestion_chunk(job_id);
        CREATE TABLE ingestion_event (
            id SERIAL PRIMARY KEY,
            job_id INTEGER NOT NULL REFERENCES ingestion_job(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL, level VARCHAR(12) NOT NULL,
            message TEXT NOT NULL
        );
        CREATE INDEX ix_ingestion_event_job_id ON ingestion_event(job_id);
    """)
    connection = op.get_bind()
    for row in connection.execute(
        sa.text("SELECT id, configuration FROM rag_configuration")
    ):
        config = row.configuration
        retrieval = config.setdefault("retrieval", {})
        config["ingestion"] = {
            "chunk_size": retrieval.pop("chunk_size", 800),
            "chunk_overlap": retrieval.pop("chunk_overlap", 100),
            "max_retries": 3,
        }
        connection.execute(
            sa.text(
                "UPDATE rag_configuration SET configuration = CAST(:config AS json) "
                "WHERE id = :id"
            ),
            {"config": json.dumps(config), "id": row.id},
        )


def downgrade():
    connection = op.get_bind()
    for row in connection.execute(
        sa.text("SELECT id, configuration FROM rag_configuration")
    ):
        config = row.configuration
        ingestion = config.pop("ingestion", {})
        config.setdefault("retrieval", {}).update(
            {
                "chunk_size": ingestion.get("chunk_size", 800),
                "chunk_overlap": ingestion.get("chunk_overlap", 100),
            }
        )
        connection.execute(
            sa.text(
                "UPDATE rag_configuration SET configuration = CAST(:config AS json) "
                "WHERE id = :id"
            ),
            {"config": json.dumps(config), "id": row.id},
        )
    for name in (
        "ingestion_event",
        "ingestion_chunk",
        "ingestion_job",
        "ingestion_source",
    ):
        op.drop_table(name)
