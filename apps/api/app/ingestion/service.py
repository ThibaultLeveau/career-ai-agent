import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.admin.models import RagConfiguration
from app.admin.schemas import RagSettings
from app.content.models import Document, Job, Project, Skill
from app.ingestion.models import ACTIVE, Chunk, Event, IngestionJob, Source

MODELS = {"jobs": Job, "projects": Project, "skills": Skill, "documents": Document}


def now():
    return datetime.now(UTC)


def settings(db: Session) -> RagSettings:
    saved = db.get(RagConfiguration, 1)
    return RagSettings.model_validate(saved.configuration) if saved else RagSettings()


def fingerprint(config: dict) -> str:
    values = {
        "embeddings": config["embeddings"],
        "ingestion": {
            k: v for k, v in config["ingestion"].items() if k != "max_retries"
        },
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def source_text(record) -> str:
    if isinstance(record, Skill):
        return f"Skill: {record.keyword}"
    if isinstance(record, Document):
        return f"Document: {record.title}\nFilename: {record.filename}"
    fields = [
        "title",
        "company",
        "location",
        "name",
        "role",
        "start_month",
        "end_month",
        "summary",
        "responsibilities",
        "achievements",
        "description",
        "outcomes",
        "website_url",
        "repository_url",
    ]
    lines = [
        f"{key.replace('_', ' ').title()}: {getattr(record, key)}"
        for key in fields
        if getattr(record, key, None)
    ]
    if record.ongoing:
        lines.append("End: Present")
    if isinstance(record, Project):
        lines.append(f"Kind: {record.kind}")
        if record.job_id:
            # Read the current relationship after job_id or a linked job changes.
            db = Session.object_session(record)
            job = db.get(Job, record.job_id)
            lines.append(f"Job: {job.title} at {job.company}")
        if record.skills:
            lines.append(
                "Skills: " + ", ".join(sorted(s.keyword for s in record.skills))
            )
    return "\n".join(lines)


def record_hash(record):
    digest = hashlib.sha256(source_text(record).encode())
    if isinstance(record, Document):
        digest.update(record.content)
    return digest.hexdigest()


def label(record):
    if isinstance(record, Job):
        return f"{record.title} · {record.company}"
    return (
        getattr(record, "name", None)
        or getattr(record, "title", None)
        or record.keyword
    )


def event(db: Session, job: IngestionJob, message: str, level="info"):
    db.add(Event(job_id=job.id, created_at=now(), level=level, message=message))


def active_job(db, source_id):
    return db.scalar(
        select(IngestionJob).where(
            IngestionJob.source_id == source_id, IngestionJob.status.in_(ACTIVE)
        )
    )


def create_job(db, source, record, trigger):
    config = settings(db).model_dump()
    job = IngestionJob(
        source_id=source.id,
        source_type=source.source_type,
        record_id=source.record_id,
        label=label(record),
        revision=source.revision,
        trigger=trigger,
        settings={"embeddings": config["embeddings"], "ingestion": config["ingestion"]},
        fingerprint=fingerprint(config),
        created_at=now(),
        available_at=now(),
    )
    db.add(job)
    db.flush()
    event(db, job, "Ingestion queued.")
    return job


def enqueue(db: Session, source_type: str, record, trigger="save", force=False):
    db.flush()
    digest = record_hash(record)
    result = db.execute(
        insert(Source)
        .values(
            source_type=source_type,
            record_id=record.id,
            revision=1,
            content_hash=digest,
        )
        .on_conflict_do_nothing()
        .returning(Source.id)
    ).scalar_one_or_none()
    source = db.scalar(
        select(Source)
        .where(Source.source_type == source_type, Source.record_id == record.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    changed = source.content_hash != digest
    if changed:
        source.revision += 1
        source.content_hash = digest
    current = active_job(db, source.id)
    if current:
        return current, False
    if not (force or changed or result):
        return None, False
    return create_job(db, source, record, trigger), True


def changed(db: Session, record):
    source_type = next(
        key for key, model in MODELS.items() if isinstance(record, model)
    )
    enqueue(db, source_type, record)
    if isinstance(record, Job):
        for project in record.projects:
            enqueue(db, "projects", project, "related_change")
    elif isinstance(record, Skill):
        for project in db.scalars(
            select(Project).where(Project.skills.any(id=record.id))
        ):
            enqueue(db, "projects", project, "related_change")


def remove(db, source_type, record_id):
    source = db.scalar(
        select(Source)
        .where(Source.source_type == source_type, Source.record_id == record_id)
        .with_for_update()
    )
    if not source:
        return
    jobs = list(
        db.scalars(
            select(IngestionJob)
            .where(IngestionJob.source_id == source.id)
            .with_for_update()
        )
    )
    for job in jobs:
        if job.status in ACTIVE:
            job.status, job.stage = "cancelled", "cancelled"
            job.finished_at, job.owner, job.lease_until = now(), None, None
            event(db, job, "Source deleted; ingestion cancelled.")
        job.plain_text = None
    db.execute(delete(Chunk).where(Chunk.job_id.in_([j.id for j in jobs])))
    db.delete(source)


def summary(db, source_type, record_id):
    source = db.scalar(
        select(Source).where(
            Source.source_type == source_type, Source.record_id == record_id
        )
    )
    return summarize(db, source, fingerprint(settings(db).model_dump()))


def summarize(db, source, current_fingerprint):
    empty = {
        "status": "not_ingested",
        "job_id": None,
        "stage": None,
        "error": None,
        "completed_chunks": 0,
        "total_chunks": 0,
    }
    if source is None:
        return empty
    job = db.scalar(
        select(IngestionJob)
        .where(IngestionJob.source_id == source.id)
        .order_by(IngestionJob.id.desc())
        .limit(1)
    )
    if job is None:
        return empty
    status = job.status
    if status == "succeeded" and (
        job.revision != source.revision or job.fingerprint != current_fingerprint
    ):
        status = "outdated"
    return {
        "status": status,
        "job_id": job.id,
        "stage": job.stage,
        "error": job.error,
        "completed_chunks": job.completed_chunks,
        "total_chunks": job.total_chunks,
    }


def bulk_enqueue(db, source_types, trigger="bulk"):
    queued, skipped, ids = 0, 0, []
    for source_type in source_types:
        for record in db.scalars(
            select(MODELS[source_type]).order_by(MODELS[source_type].id)
        ):
            job, created = enqueue(db, source_type, record, trigger, force=True)
            queued += int(created)
            skipped += int(not created)
            if created:
                ids.append(job.id)
    return {"queued": queued, "skipped": skipped, "job_ids": ids}
