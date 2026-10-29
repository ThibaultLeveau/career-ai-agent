from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.content import public
from app.content.models import Job, Project
from app.db import get_session

router = APIRouter(prefix="/public", tags=["portfolio"])
Database = Annotated[Session, Depends(get_session)]
RecordId = Annotated[int, Path(gt=0)]


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
