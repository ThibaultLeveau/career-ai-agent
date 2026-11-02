from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.content import public
from app.content.models import Job, Project
from app.content.resume_download import download_document_id, eligible_resume
from app.db import get_session

router = APIRouter(prefix="/public", tags=["portfolio"])
Database = Annotated[Session, Depends(get_session)]
RecordId = Annotated[int, Path(gt=0)]


@router.get("/resumes/download")
def download_resume(
    token: Annotated[str, Query(min_length=1, max_length=2048)], db: Database
):
    try:
        document_id = download_document_id(token)
        record = eligible_resume(db, document_id)
        if record is None:
            raise ValueError("Resume unavailable")
        return Response(
            record.content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''"
                + quote(record.filename, safe=""),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )
    except ValueError:
        raise HTTPException(404, "This resume is no longer available.") from None
    except SQLAlchemyError:
        raise HTTPException(
            503, "The resume could not be downloaded. Please try again."
        ) from None


def read_catalog(db, model, filters):
    try:
        return public.catalog(db, model, filters)
    except SQLAlchemyError:
        raise HTTPException(
            503, "This collection could not be loaded. Please try again."
        ) from None


def read_detail(db, model, record_id):
    try:
        record = public.detail(db, model, record_id)
    except SQLAlchemyError:
        raise HTTPException(
            503, "This experience could not be loaded. Please try again."
        ) from None
    if record is None:
        raise HTTPException(404, "Experience not found")
    return record


@router.get("/jobs", response_model=public.Catalog[public.JobRow])
def jobs(filters: Annotated[public.JobFilters, Query()], db: Database):
    return read_catalog(db, Job, filters)


@router.get("/jobs/{record_id}", response_model=public.JobDetail)
def job(record_id: RecordId, db: Database):
    return read_detail(db, Job, record_id)


@router.get("/projects", response_model=public.Catalog[public.ProjectRow])
def projects(filters: Annotated[public.ProjectFilters, Query()], db: Database):
    return read_catalog(db, Project, filters)


@router.get("/projects/{record_id}", response_model=public.ProjectDetail)
def project(record_id: RecordId, db: Database):
    return read_detail(db, Project, record_id)
