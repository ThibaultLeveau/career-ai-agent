from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.security import Database, check_origin, require_admin
from app.content.models import Document, Job, Project, Skill
from app.content.schemas import (
    DocumentInput,
    DocumentOutput,
    JobInput,
    JobOutput,
    ProjectInput,
    ProjectOutput,
    SkillInput,
    SkillOutput,
)
from app.db import Base
from app.ingestion.service import changed, enqueue, remove

router = APIRouter(
    prefix="/admin",
    tags=["content"],
    dependencies=[Depends(check_origin), Depends(require_admin)],
)
MAX_PDF_SIZE = 10 * 1024 * 1024


def get_record[T: Base](model: type[T], record_id: int, db: Session) -> T:
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(404, "Record not found")
    return record


def save[T: Base](record: T, db: Session) -> T:
    db.add(record)
    try:
        changed(db, record)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            409, "A related record changed. Refresh and try again."
        ) from error
    db.refresh(record)
    return record


@router.get("/jobs", response_model=list[JobOutput])
def jobs(db: Database):
    return db.scalars(
        select(Job).order_by(Job.start_month.desc().nulls_last(), Job.id.desc())
    ).all()


@router.post("/jobs", response_model=JobOutput, status_code=201)
def create_job(data: JobInput, db: Database):
    return save(Job(**data.model_dump()), db)


@router.get("/jobs/{record_id}", response_model=JobOutput)
def job(record_id: int, db: Database):
    return get_record(Job, record_id, db)


@router.put("/jobs/{record_id}", response_model=JobOutput)
def update_job(record_id: int, data: JobInput, db: Database):
    record = get_record(Job, record_id, db)
    for key, value in data.model_dump().items():
        setattr(record, key, value)
    return save(record, db)


@router.delete("/jobs/{record_id}", status_code=204)
def delete_job(record_id: int, db: Database):
    record = get_record(Job, record_id, db)
    if record.projects:
        raise HTTPException(
            409, "Reassign, unlink, or delete this job's projects first."
        )
    remove(db, "jobs", record_id)
    db.delete(record)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            409, "Reassign, unlink, or delete this job's projects first."
        ) from error


@router.get("/projects", response_model=list[ProjectOutput])
def projects(db: Database):
    return db.scalars(
        select(Project).order_by(Project.updated_at.desc(), Project.id.desc())
    ).all()


def project_values(data: ProjectInput, db: Session):
    if data.job_id is not None and db.get(Job, data.job_id) is None:
        raise HTTPException(422, "Selected job no longer exists")
    skills = list(db.scalars(select(Skill).where(Skill.id.in_(set(data.skill_ids)))))
    if len(skills) != len(set(data.skill_ids)):
        raise HTTPException(422, "One or more selected skills no longer exist")
    return {**data.model_dump(exclude={"skill_ids"}), "skills": skills}


@router.post("/projects", response_model=ProjectOutput, status_code=201)
def create_project(data: ProjectInput, db: Database):
    return save(Project(**project_values(data, db)), db)


@router.get("/projects/{record_id}", response_model=ProjectOutput)
def project(record_id: int, db: Database):
    return get_record(Project, record_id, db)


@router.put("/projects/{record_id}", response_model=ProjectOutput)
def update_project(record_id: int, data: ProjectInput, db: Database):
    record = get_record(Project, record_id, db)
    for key, value in project_values(data, db).items():
        setattr(record, key, value)
    record.updated_at = func.now()
    return save(record, db)


@router.delete("/projects/{record_id}", status_code=204)
def delete_project(record_id: int, db: Database):
    remove(db, "projects", record_id)
    db.delete(get_record(Project, record_id, db))
    db.commit()


@router.get("/skills", response_model=list[SkillOutput])
def skills(db: Database):
    return db.scalars(select(Skill).order_by(func.lower(Skill.keyword), Skill.id)).all()


def save_skill(record: Skill, data: SkillInput, db: Session) -> Skill:
    record.keyword = data.keyword
    db.add(record)
    try:
        changed(db, record)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "This skill already exists") from error
    db.refresh(record)
    return record


@router.post("/skills", response_model=SkillOutput, status_code=201)
def create_skill(data: SkillInput, db: Database):
    return save_skill(Skill(), data, db)


@router.get("/skills/{record_id}", response_model=SkillOutput)
def skill(record_id: int, db: Database):
    return get_record(Skill, record_id, db)


@router.put("/skills/{record_id}", response_model=SkillOutput)
def update_skill(record_id: int, data: SkillInput, db: Database):
    return save_skill(get_record(Skill, record_id, db), data, db)


@router.delete("/skills/{record_id}", status_code=204)
def delete_skill(record_id: int, db: Database):
    record = get_record(Skill, record_id, db)
    projects = list(db.scalars(select(Project).where(Project.skills.any(id=record_id))))
    remove(db, "skills", record_id)
    for project in projects:
        project.skills = [skill for skill in project.skills if skill.id != record_id]
        enqueue(db, "projects", project, "related_change")
    db.delete(record)
    db.commit()


@router.get("/documents", response_model=list[DocumentOutput])
def documents(db: Database):
    return db.scalars(
        select(Document).order_by(Document.created_at.desc(), Document.id.desc())
    ).all()


def document_values(title: str, file: UploadFile | None):
    try:
        values = DocumentInput(title=title).model_dump()
    except ValidationError as error:
        raise HTTPException(
            422, "Title must contain between 1 and 200 characters"
        ) from error
    if file is not None:
        filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        filename = "".join(c for c in filename if c.isprintable())[:255]
        if (
            not filename.lower().endswith(".pdf")
            or file.content_type != "application/pdf"
        ):
            raise HTTPException(422, "Choose a PDF file")
        content = file.file.read(MAX_PDF_SIZE + 1)
        if len(content) > MAX_PDF_SIZE:
            raise HTTPException(413, "PDF files must be 10 MiB or smaller")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(422, "The file does not have a valid PDF signature")
        values.update(filename=filename, size=len(content), content=content)
    return values


@router.post("/documents", response_model=DocumentOutput, status_code=201)
def create_document(
    db: Database, title: Annotated[str, Form()], file: Annotated[UploadFile, File()]
):
    return save(Document(**document_values(title, file)), db)


@router.get("/documents/{record_id}", response_model=DocumentOutput)
def document(record_id: int, db: Database):
    return get_record(Document, record_id, db)


@router.put("/documents/{record_id}", response_model=DocumentOutput)
def update_document(
    record_id: int,
    db: Database,
    title: Annotated[str, Form()],
    file: Annotated[UploadFile | None, File()] = None,
):
    record = get_record(Document, record_id, db)
    for key, value in document_values(title, file).items():
        setattr(record, key, value)
    return save(record, db)


@router.get("/documents/{record_id}/file")
def download_document(record_id: int, db: Database):
    record = get_record(Document, record_id, db)
    return Response(
        record.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''"
            + quote(record.filename, safe=""),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/documents/{record_id}", status_code=204)
def delete_document(record_id: int, db: Database):
    remove(db, "documents", record_id)
    db.delete(get_record(Document, record_id, db))
    db.commit()
