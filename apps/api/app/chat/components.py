"""Verified career views and stateless, authenticated navigation scopes."""

from dataclasses import dataclass
from typing import Annotated, Literal

from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.admin.schemas import ChatComponents
from app.admin.security import cipher
from app.chat.schemas import DetailAction
from app.content.models import Job, Project, Skill

Entity = Literal["projects", "jobs"]
ComponentKind = Literal["project_list", "project_card", "job_list", "job_card"]
RecordId = Annotated[int, Field(gt=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ListScope(StrictModel):
    purpose: Literal["career_list"] = "career_list"
    entity: Entity
    ids: list[RecordId] = Field(max_length=10000)
    page_size: int = Field(ge=1, le=20)


class DetailScope(StrictModel):
    purpose: Literal["career_detail"] = "career_detail"
    entity: Entity
    id: RecordId


class PageRequest(StrictModel):
    token: str = Field(min_length=1, max_length=240000)
    filter: str = Field(default="", max_length=200)
    page: int = Field(default=1, ge=1, le=10000)


class ComponentError(ValueError):
    pass


def seal(scope: ListScope | DetailScope) -> str:
    return cipher().encrypt(scope.model_dump_json().encode()).decode()


def unseal(token: str, schema):
    try:
        return schema.model_validate_json(cipher().decrypt(token.encode()))
    except InvalidToken, ValidationError, ValueError:
        raise ComponentError(
            "This career view is unavailable. Please ask for a fresh list."
        ) from None


class Timeline(StrictModel):
    id: int
    start_month: str | None
    end_month: str | None
    ongoing: bool
    summary: str
    action: DetailAction


class LinkedJob(StrictModel):
    id: int
    title: str
    company: str


class ProjectRow(Timeline):
    name: str
    role: str
    kind: Literal["personal", "professional"]
    job: LinkedJob | None
    skills: list[str]


class JobRow(Timeline):
    title: str
    company: str
    location: str


class ProjectDetails(ProjectRow):
    description: str
    outcomes: str


class JobDetails(JobRow):
    responsibilities: str
    achievements: str


class ListPage(StrictModel):
    token: str
    total: int
    matched_total: int
    page: int
    page_size: int
    filter: str


class ProjectList(ListPage):
    type: Literal["project_list"] = "project_list"
    items: list[ProjectRow]


class JobList(ListPage):
    type: Literal["job_list"] = "job_list"
    items: list[JobRow]


class ProjectCard(StrictModel):
    type: Literal["project_card"] = "project_card"
    record: ProjectDetails


class JobCard(StrictModel):
    type: Literal["job_card"] = "job_card"
    record: JobDetails


class ComponentEvent(StrictModel):
    introduction: str = Field(min_length=1, max_length=1600)
    component: Annotated[
        ProjectList | JobList | ProjectCard | JobCard, Field(discriminator="type")
    ]


class Selection(StrictModel):
    type: ComponentKind
    reference: str = Field(min_length=1, max_length=100)
    introduction: str = Field(min_length=1, max_length=1600)


class Presentation(StrictModel):
    components: list[Selection] = Field(default_factory=list, max_length=4)


@dataclass(frozen=True)
class Target:
    type: ComponentKind
    ids: list[int]
    match_type: str = "exact"
    label: str = ""

    @property
    def entity(self) -> Entity:
        return "projects" if self.type.startswith("project_") else "jobs"


def timeline(record, *, details=False) -> dict:
    entity = "projects" if isinstance(record, Project) else "jobs"
    summary = record.summary
    if not details:
        summary = summary or (
            record.description if entity == "projects" else record.responsibilities
        )
        summary = summary[:320].rstrip() + ("…" if len(summary) > 320 else "")
    return {
        "id": record.id,
        "start_month": record.start_month,
        "end_month": record.end_month,
        "ongoing": record.ongoing,
        "summary": summary,
        "action": DetailAction(
            type="show_project" if entity == "projects" else "show_job",
            token=seal(DetailScope(entity=entity, id=record.id)),
        ),
    }


def project_row(record: Project, *, details=False) -> ProjectRow:
    fields = {
        **timeline(record, details=details),
        "name": record.name,
        "role": record.role,
        "kind": record.kind,
        "job": LinkedJob(
            id=record.job.id, title=record.job.title, company=record.job.company
        )
        if record.job
        else None,
        "skills": [skill.keyword for skill in record.skills],
    }
    return (
        ProjectDetails(
            **fields, description=record.description, outcomes=record.outcomes
        )
        if details
        else ProjectRow(**fields)
    )


def job_row(record: Job, *, details=False) -> JobRow:
    fields = {
        **timeline(record, details=details),
        "title": record.title,
        "company": record.company,
        "location": record.location,
    }
    return (
        JobDetails(
            **fields,
            responsibilities=record.responsibilities,
            achievements=record.achievements,
        )
        if details
        else JobRow(**fields)
    )


def page(db: Session, request: PageRequest) -> ProjectList | JobList:
    scope = unseal(request.token, ListScope)
    model = Project if scope.entity == "projects" else Job
    conditions = [model.id.in_(scope.ids)]
    total = db.scalar(select(func.count()).select_from(model).where(*conditions))
    if request.filter:
        term = request.filter
        skill = Skill.keyword.icontains(term, autoescape=True)
        conditions.append(
            or_(
                Project.name.icontains(term, autoescape=True),
                Project.role.icontains(term, autoescape=True),
                func.coalesce(
                    func.nullif(Project.summary, ""), Project.description
                ).icontains(term, autoescape=True),
                Project.skills.any(skill),
                Project.job.has(
                    or_(
                        Job.company.icontains(term, autoescape=True),
                        Job.title.icontains(term, autoescape=True),
                    )
                ),
            )
            if model is Project
            else or_(
                Job.title.icontains(term, autoescape=True),
                Job.company.icontains(term, autoescape=True),
                func.coalesce(
                    func.nullif(Job.summary, ""), Job.responsibilities
                ).icontains(term, autoescape=True),
                Job.projects.any(Project.skills.any(skill)),
            )
        )
    matched = db.scalar(select(func.count()).select_from(model).where(*conditions))
    current = min(
        request.page, max(1, (matched + scope.page_size - 1) // scope.page_size)
    )
    rows = (
        db.scalars(
            select(model)
            .where(*conditions)
            .order_by(
                case({id: index for index, id in enumerate(scope.ids)}, value=model.id)
            )
            .offset((current - 1) * scope.page_size)
            .limit(scope.page_size)
        ).all()
        if scope.ids
        else []
    )
    fields = {
        "token": request.token,
        "total": total,
        "matched_total": matched,
        "page": current,
        "page_size": scope.page_size,
        "filter": request.filter,
    }
    return (
        ProjectList(**fields, items=[project_row(row) for row in rows])
        if model is Project
        else JobList(**fields, items=[job_row(row) for row in rows])
    )


def card(db: Session, entity: Entity, id: int) -> ProjectCard | JobCard:
    model = Project if entity == "projects" else Job
    record = db.get(model, id)
    if record is None:
        raise ComponentError(
            "This record is no longer available. Please ask for an updated list."
        )
    return (
        ProjectCard(record=project_row(record, details=True))
        if entity == "projects"
        else JobCard(record=job_row(record, details=True))
    )


def associated_projects(db: Session, job_id: int) -> list[int]:
    return list(
        db.scalars(
            select(Project.id)
            .where(Project.job_id == job_id)
            .order_by(Project.start_month.desc().nulls_last(), Project.id.desc())
            .limit(10001)
        )
    )


def render(db: Session, target: Target, config: ChatComponents):
    if target.type.endswith("_card"):
        return card(db, target.entity, target.ids[0])
    size = (
        config.project_list_page_size
        if target.entity == "projects"
        else config.job_list_page_size
    )
    scope = ListScope(entity=target.entity, ids=target.ids, page_size=size)
    return page(db, PageRequest(token=seal(scope)))


def detail_scope(action: DetailAction) -> DetailScope:
    scope = unseal(action.token, DetailScope)
    expected = "show_project" if scope.entity == "projects" else "show_job"
    if action.type != expected:
        raise ComponentError(
            "This detail link is invalid. Please ask for a fresh list."
        )
    return scope
