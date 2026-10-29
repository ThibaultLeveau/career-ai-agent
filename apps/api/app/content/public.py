"""Read-only portfolio queries and explicit visitor-facing record projections."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.content.models import Job, Project, Skill, project_skill


class PublicModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PublicSkill(PublicModel):
    id: int
    keyword: str


class LinkedJob(PublicModel):
    id: int
    title: str
    company: str


class Timeline(PublicModel):
    id: int
    start_month: str | None
    end_month: str | None
    ongoing: bool
    summary: str


class ProjectRow(Timeline):
    name: str
    role: str
    kind: Literal["personal", "professional"]
    job: LinkedJob | None
    skills: list[PublicSkill]


class JobRow(Timeline):
    title: str
    company: str
    location: str
    skills: list[PublicSkill]
    project_count: int


class ProjectDetail(ProjectRow):
    description: str
    contribution: str
    outcomes: str
    website_url: str
    repository_url: str


class JobDetail(JobRow):
    responsibilities: str
    achievements: str
    projects: list[ProjectRow]


class Facets(BaseModel):
    companies: list[str] = Field(default_factory=list)
    skills: list[PublicSkill] = Field(default_factory=list)
    jobs: list[LinkedJob] = Field(default_factory=list)


class Catalog[T](BaseModel):
    items: list[T]
    total: int
    matched_total: int
    page: int
    page_size: int
    facets: Facets


class Filters(BaseModel):
    q: str = Field(default="", max_length=200)
    status: Literal["ongoing", "past"] | None = None
    skill_id: int | None = Field(default=None, gt=0)
    page: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=12, ge=1, le=48)


class JobFilters(Filters):
    company: str | None = Field(default=None, max_length=200)


class ProjectFilters(Filters):
    kind: Literal["personal", "professional"] | None = None
    job_id: int | None = Field(default=None, gt=0)


PROJECT_OPTIONS = (
    joinedload(Project.job).lazyload(Job.projects),
    selectinload(Project.skills),
)
JOB_OPTIONS = (selectinload(Job.projects).selectinload(Project.skills),)


def timeline(record: Job | Project, *, details: bool) -> dict:
    return {
        "id": record.id,
        "start_month": record.start_month,
        "end_month": record.end_month,
        "ongoing": record.ongoing,
        "summary": record.summary if details else record.small_summary,
    }


def project_row(record: Project, *, details: bool = False) -> ProjectRow:
    fields = {
        **timeline(record, details=details),
        "name": record.name,
        "role": record.role,
        "kind": record.kind,
        "job": LinkedJob.model_validate(record.job) if record.job else None,
        "skills": record.skills,
    }
    if details:
        return ProjectDetail(
            **fields,
            description=record.description,
            contribution=record.contribution,
            outcomes=record.outcomes,
            website_url=record.website_url,
            repository_url=record.repository_url,
        )
    return ProjectRow(**fields)


def job_row(record: Job, *, details: bool = False) -> JobRow:
    skills = {
        skill.id: skill for project in record.projects for skill in project.skills
    }
    fields = {
        **timeline(record, details=details),
        "title": record.title,
        "company": record.company,
        "location": record.location,
        "skills": sorted(skills.values(), key=lambda skill: skill.keyword.casefold()),
        "project_count": len(record.projects),
    }
    if details:
        projects = sorted(
            record.projects,
            key=lambda project: (project.start_month or "", project.id),
            reverse=True,
        )
        return JobDetail(
            **fields,
            responsibilities=record.responsibilities,
            achievements=record.achievements,
            projects=[project_row(project) for project in projects],
        )
    return JobRow(**fields)


def conditions(model: type[Job] | type[Project], filters: Filters) -> list:
    result = []
    if filters.status:
        result.append(model.ongoing.is_(filters.status == "ongoing"))
    if filters.skill_id is not None:
        skill = Project.skills.any(Skill.id == filters.skill_id)
        result.append(skill if model is Project else Job.projects.any(skill))
    if isinstance(filters, JobFilters) and filters.company is not None:
        result.append(Job.company == filters.company)
    if isinstance(filters, ProjectFilters):
        if filters.kind:
            result.append(
                Project.job_id.is_(None)
                if filters.kind == "personal"
                else Project.job_id.is_not(None)
            )
        if filters.job_id is not None:
            result.append(Project.job_id == filters.job_id)
    if term := filters.q.strip():
        skills = Project.skills.any(Skill.keyword.icontains(term, autoescape=True))
        if model is Job:
            fields = (
                Job.title,
                Job.company,
                Job.location,
                Job.small_summary,
                Job.summary,
                Job.responsibilities,
                Job.achievements,
            )
            related = [Job.projects.any(skills)]
        else:
            fields = (
                Project.name,
                Project.role,
                Project.small_summary,
                Project.summary,
                Project.description,
                Project.contribution,
                Project.outcomes,
            )
            related = [
                skills,
                Project.job.has(
                    or_(
                        Job.company.icontains(term, autoescape=True),
                        Job.title.icontains(term, autoescape=True),
                    )
                ),
            ]
        result.append(
            or_(*(field.icontains(term, autoescape=True) for field in fields), *related)
        )
    return result


def facets(db: Session, model: type[Job] | type[Project]) -> Facets:
    skills = select(Skill).join(project_skill).join(Project)
    if model is Job:
        skills = skills.where(Project.job_id.is_not(None))
        companies = sorted(
            db.scalars(select(Job.company).distinct()).all(), key=str.casefold
        )
        jobs = []
    else:
        companies = []
        jobs = sorted(
            db.execute(select(Job.id, Job.title, Job.company).join(Project).distinct())
            .mappings()
            .all(),
            key=lambda job: (
                job["company"].casefold(),
                job["title"].casefold(),
                job["id"],
            ),
        )
    return Facets(
        companies=companies,
        jobs=[LinkedJob.model_validate(job) for job in jobs],
        skills=sorted(
            db.scalars(skills.distinct()).all(),
            key=lambda skill: skill.keyword.casefold(),
        ),
    )


def catalog(db: Session, model: type[Job] | type[Project], filters: Filters) -> Catalog:
    where = conditions(model, filters)
    total = db.scalar(select(func.count()).select_from(model)) or 0
    matched = db.scalar(select(func.count()).select_from(model).where(*where)) or 0
    page = min(
        filters.page, max(1, (matched + filters.page_size - 1) // filters.page_size)
    )
    records = db.scalars(
        select(model)
        .where(*where)
        .options(*(JOB_OPTIONS if model is Job else PROJECT_OPTIONS))
        .order_by(model.start_month.desc().nulls_last(), model.id.desc())
        .offset((page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()
    serialize = job_row if model is Job else project_row
    return Catalog(
        items=[serialize(record) for record in records],
        total=total,
        matched_total=matched,
        page=page,
        page_size=filters.page_size,
        facets=facets(db, model),
    )


def detail(db: Session, model: type[Job] | type[Project], record_id: int):
    record = db.scalar(
        select(model)
        .where(model.id == record_id)
        .options(*(JOB_OPTIONS if model is Job else PROJECT_OPTIONS))
    )
    if record is None:
        return None
    return (
        job_row(record, details=True)
        if model is Job
        else project_row(record, details=True)
    )
