"""Retire standalone skill embeddings while retaining content and audit history."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO ingestion_event (job_id, created_at, level, message)
        SELECT id, now(), 'info',
            'Standalone skill ingestion retired; keywords remain in project documents.'
        FROM ingestion_job WHERE source_type = 'skills';
        UPDATE ingestion_job
        SET status = 'cancelled', stage = 'cancelled', finished_at = now(),
            owner = NULL, lease_until = NULL
        WHERE source_type = 'skills' AND status IN ('queued', 'running', 'retrying');
        UPDATE ingestion_source SET active_job_id = NULL WHERE source_type = 'skills';
        DELETE FROM ingestion_chunk
        WHERE job_id IN (SELECT id FROM ingestion_job WHERE source_type = 'skills');
        UPDATE ingestion_job SET plain_text = NULL WHERE source_type = 'skills';
    """)


def downgrade():
    # Derived vectors cannot be restored. Older code can re-ingest retained skills.
    pass
