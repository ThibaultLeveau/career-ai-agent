import logging
import random
import signal
import threading
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from cryptography.fernet import InvalidToken
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.admin.models import ProviderKey
from app.admin.security import cipher
from app.content.models import Document
from app.db import get_engine
from app.ingestion.models import Chunk, IngestionJob, Source
from app.ingestion.pdf import extract as extract_pdf
from app.ingestion.provider import embed
from app.ingestion.service import MODELS, create_job, event, now, source_text
from app.ingestion.text import IngestionError, chunk_text, normalize

log = logging.getLogger(__name__)
LEASE_SECONDS = 120


def session():
    return Session(get_engine())


def claim(db):
    job = db.scalar(
        select(IngestionJob)
        .where(
            IngestionJob.source_type.in_(MODELS),
            or_(
                (IngestionJob.status.in_(("queued", "retrying")))
                & (IngestionJob.available_at <= now()),
                (IngestionJob.status == "running") & (IngestionJob.lease_until < now()),
            ),
        )
        .order_by(IngestionJob.available_at, IngestionJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    if job.status == "running":
        job.retries += 1
        event(db, job, "Worker lease expired; recovering unfinished work.", "warning")
    job.status = "running"
    job.owner = str(uuid.uuid4())
    job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
    job.started_at = job.started_at or now()
    event(db, job, "Worker started processing.")
    db.commit()
    return job.id, job.owner


def owned(db, job_id, owner):
    source_id = db.scalar(
        select(IngestionJob.source_id).where(IngestionJob.id == job_id)
    )
    if source_id is None:
        return None, None
    source = db.scalar(select(Source).where(Source.id == source_id).with_for_update())
    job = db.scalar(
        select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
    )
    if (
        not source
        or not job
        or job.source_type not in MODELS
        or job.status != "running"
        or job.owner != owner
        or job.lease_until <= now()
    ):
        return None, None
    return source, job


def finish(db, source, job, status, message):
    job.status, job.stage = status, status
    job.finished_at, job.lease_until, job.owner = now(), None, None
    event(db, job, message, "error" if status == "failed" else "info")
    db.flush()
    if source.revision != job.revision:
        record = db.get(MODELS[source.source_type], source.record_id)
        if record:
            create_job(db, source, record, "newer_revision")


@contextmanager
def heartbeat(job_id, owner):
    stop = threading.Event()

    def beat():
        while not stop.wait(10):
            try:
                with session() as db:
                    result = db.execute(
                        update(IngestionJob)
                        .where(
                            IngestionJob.id == job_id,
                            IngestionJob.owner == owner,
                            IngestionJob.status == "running",
                            IngestionJob.lease_until > now(),
                        )
                        .values(lease_until=now() + timedelta(seconds=LEASE_SECONDS))
                    )
                    db.commit()
                    if not result.rowcount:
                        return
                    Path("/tmp/ingestion-heartbeat").touch()
            except Exception:
                log.warning("Could not renew ingestion lease for job %s", job_id)

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=6)


def process(job_id, owner):
    with session() as db:
        source, job = owned(db, job_id, owner)
        if job is None:
            return
        if source.revision != job.revision:
            finish(
                db,
                source,
                job,
                "superseded",
                "Newer content is available; scheduling its ingestion.",
            )
            db.commit()
            return
        if job.retries > job.settings["ingestion"]["max_retries"]:
            raise IngestionError(
                "Worker recovery retry limit reached. Re-ingest to try again."
            )
        config = job.settings
        saved_key = db.get(ProviderKey, "openai")
        if not saved_key:
            raise IngestionError(
                "Add an OpenAI API key in AI Provider settings, then re-ingest."
            )
        try:
            key = cipher().decrypt(saved_key.encrypted_key.encode()).decode()
        except InvalidToken, ValueError:
            raise IngestionError(
                "The saved API key could not be decrypted. Replace it in AI settings."
            ) from None
        needs_text = job.total_chunks == 0
        if needs_text:
            record = db.get(MODELS[source.source_type], source.record_id)
            text = normalize(source_text(record))
            content = record.content if isinstance(record, Document) else None
            job.stage = "extracting"
            event(db, job, "Extracting source text.")
        db.commit()
    if needs_text:
        pages = [(None, text)]
        if content is not None:
            pages += extract_pdf(content)
        plain_text, chunks = chunk_text(
            pages,
            config["ingestion"]["chunk_size"],
            config["ingestion"]["chunk_overlap"],
        )
        with session() as db:
            source, job = owned(db, job_id, owner)
            if job is None:
                return
            if source.revision != job.revision:
                finish(
                    db, source, job, "superseded", "Source changed during extraction."
                )
                db.commit()
                return
            job.plain_text, job.total_chunks, job.stage = (
                plain_text,
                len(chunks),
                "embedding",
            )
            for position, chunk in enumerate(chunks):
                db.add(
                    Chunk(
                        job_id=job.id,
                        position=position,
                        text=chunk.text,
                        token_count=chunk.token_count,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                    )
                )
            event(
                db,
                job,
                f"Created {len(chunks)} overlapping chunks "
                f"from {len(plain_text)} characters.",
            )
            db.commit()
    while True:
        with session() as db:
            source, job = owned(db, job_id, owner)
            if job is None:
                return
            if source.revision != job.revision:
                finish(
                    db,
                    source,
                    job,
                    "superseded",
                    "Source changed; newer content will be ingested.",
                )
                db.commit()
                return
            candidates = list(
                db.scalars(
                    select(Chunk)
                    .where(Chunk.job_id == job_id, Chunk.embedding.is_(None))
                    .order_by(Chunk.position)
                    .limit(32)
                )
            )
            batch, token_count = [], 0
            for chunk in candidates:
                if batch and token_count + chunk.token_count > 16000:
                    break
                batch.append((chunk.id, chunk.text))
                token_count += chunk.token_count
            if not batch:
                source.active_job_id = job.id
                previous = select(IngestionJob.id).where(
                    IngestionJob.source_id == source.id, IngestionJob.id != job.id
                )
                db.execute(delete(Chunk).where(Chunk.job_id.in_(previous)))
                db.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id.in_(previous))
                    .values(plain_text=None)
                )
                job.error = None
                finish(
                    db,
                    source,
                    job,
                    "succeeded",
                    f"Ingestion completed: {job.total_chunks} chunks embedded.",
                )
                db.commit()
                return
            job.stage = "embedding"
            db.commit()
        vectors = embed([text for _, text in batch], config["embeddings"], key)
        with session() as db:
            source, job = owned(db, job_id, owner)
            if job is None:
                return
            for (chunk_id, _), vector in zip(batch, vectors, strict=True):
                db.execute(
                    update(Chunk).where(Chunk.id == chunk_id).values(embedding=vector)
                )
            job.completed_chunks += len(batch)
            event(
                db, job, f"Embedded {job.completed_chunks}/{job.total_chunks} chunks."
            )
            db.commit()


def failure(job_id, owner, error):
    with session() as db:
        source, job = owned(db, job_id, owner)
        if job is None:
            return
        job.error = str(error)
        if source.revision != job.revision:
            finish(
                db,
                source,
                job,
                "superseded",
                "Source changed; scheduling the latest revision.",
            )
        elif error.retryable and job.retries < job.settings["ingestion"]["max_retries"]:
            job.retries += 1
            delay = max(error.delay, min(60, 2**job.retries)) + random.uniform(0, 1)
            # Extremely long provider delays remain visible for manual retry.
            if delay > 86400:
                finish(
                    db,
                    source,
                    job,
                    "failed",
                    "Provider requested a delay over 24 hours. Re-ingest later.",
                )
            else:
                job.status, job.stage = "retrying", "waiting"
                job.available_at = now() + timedelta(seconds=delay)
                job.owner, job.lease_until = None, None
                event(
                    db,
                    job,
                    f"{error} Retry {job.retries} scheduled in {delay:.0f}s.",
                    "warning",
                )
        else:
            finish(db, source, job, "failed", str(error))
        db.commit()


def run_one():
    with session() as db:
        claimed = claim(db)
    if claimed is None:
        return False
    job_id, owner = claimed
    with heartbeat(job_id, owner):
        try:
            process(job_id, owner)
        except IngestionError as error:
            failure(job_id, owner, error)
        except Exception:
            log.warning("Unexpected ingestion failure for job %s", job_id)
            failure(
                job_id,
                owner,
                IngestionError(
                    "An internal ingestion error occurred. Re-ingest to try again.",
                    True,
                ),
            )
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            worked = run_one()
            Path("/tmp/ingestion-heartbeat").touch()
            if not worked:
                stop.wait(1)
        except Exception:
            log.warning("Worker could not access the queue; retrying in 5 seconds.")
            stop.wait(5)


if __name__ == "__main__":
    main()
