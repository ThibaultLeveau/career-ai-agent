from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.admin.security import Database, check_origin, require_admin
from app.content.models import Skill
from app.ingestion.models import ACTIVE, Event, IngestionJob
from app.ingestion.service import (
    MODELS,
    bulk_enqueue,
    enqueue,
    fingerprint,
    settings,
    summaries,
)

SourceType = Literal["jobs", "projects", "documents"]
HistorySourceType = Literal["jobs", "projects", "skills", "documents"]
Status = Literal[
    "queued", "running", "retrying", "succeeded", "failed", "cancelled", "superseded"
]
router = APIRouter(
    prefix="/admin",
    tags=["ingestion"],
    dependencies=[Depends(check_origin), Depends(require_admin)],
)


class BulkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_types: list[SourceType] = Field(min_length=1, max_length=3)


def output(job):
    fields = (
        "id",
        "source_type",
        "record_id",
        "label",
        "trigger",
        "status",
        "stage",
        "settings",
        "total_chunks",
        "completed_chunks",
        "retries",
        "error",
        "created_at",
        "started_at",
        "finished_at",
        "available_at",
    )
    return {
        **{field: getattr(job, field) for field in fields},
        "source_deleted": job.source_id is None,
    }


@router.get("/ingestion/status")
def statuses(db: Database, source_type: SourceType):
    return summaries(db, source_type)


@router.get("/overview")
def overview(db: Database):
    current = fingerprint(settings(db).model_dump())
    counts = {"skills": db.scalar(select(func.count()).select_from(Skill))}
    ingestion = {"pending": 0, "ongoing": 0, "failed": 0, "successful": 0}
    groups = {
        "running": "ongoing",
        "retrying": "ongoing",
        "failed": "failed",
        "succeeded": "successful",
    }
    active = False
    for source_type in MODELS:
        items = summaries(db, source_type, current)
        counts[source_type] = len(items)
        for item in items.values():
            active = active or item["status"] in ACTIVE
            ingestion[groups.get(item["status"], "pending")] += 1
    return {"counts": counts, "ingestion": ingestion, "active": active}


@router.get("/ingestion/jobs")
def jobs(
    db: Database,
    source_type: HistorySourceType | None = None,
    status: Status | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    query = select(IngestionJob)
    if source_type:
        query = query.where(IngestionJob.source_type == source_type)
    if status:
        query = query.where(IngestionJob.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    records = db.scalars(
        query.order_by(IngestionJob.id.desc()).offset(offset).limit(limit)
    )
    return {
        "items": [output(job) for job in records],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def get_job(db, job_id):
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(404, "Ingestion job not found")
    return job


@router.get("/ingestion/jobs/{job_id}")
def job_detail(job_id: int, db: Database):
    return output(get_job(db, job_id))


@router.get("/ingestion/jobs/{job_id}/logs")
def logs(job_id: int, db: Database, after_id: Annotated[int, Query(ge=0)] = 0):
    get_job(db, job_id)
    events = db.scalars(
        select(Event)
        .where(Event.job_id == job_id, Event.id > after_id)
        .order_by(Event.id)
        .limit(200)
    )
    return [
        {
            "id": item.id,
            "created_at": item.created_at,
            "level": item.level,
            "message": item.message,
        }
        for item in events
    ]


@router.post("/ingestion/reingest", status_code=202)
def reingest_all(data: BulkInput, db: Database):
    result = bulk_enqueue(db, sorted(set(data.source_types)))
    db.commit()
    return result


@router.post("/ingestion/{source_type}/{record_id}/reingest", status_code=202)
def reingest(source_type: SourceType, record_id: int, db: Database):
    record = db.get(MODELS[source_type], record_id)
    if record is None:
        raise HTTPException(404, "Record not found")
    job, created = enqueue(db, source_type, record, "manual", force=True)
    if not created:
        raise HTTPException(409, f"Ingestion job #{job.id} is already in progress.")
    db.commit()
    return output(job)
