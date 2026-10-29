import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, false, func, not_, or_, select
from sqlalchemy.orm import Session

from app.content.models import Job, Project, Skill
from app.ingestion.service import label, source_text

Term = Annotated[str, Field(min_length=1, max_length=200)]
Month = Annotated[str, Field(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$")]
SourceRef = tuple[Literal["projects", "jobs"], int]


class QueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SkillExpression(QueryModel):
    op: Literal["term", "and", "or", "not"] = "term"
    value: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    children: list[SkillExpression] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def valid_expression(self) -> Self:
        if self.op == "term":
            if not self.value or self.children:
                raise ValueError("A skill term requires a value and no children")
        elif self.value is not None or not self.children:
            raise ValueError("A Boolean skill expression requires children only")
        elif self.op == "not" and len(self.children) != 1:
            raise ValueError("NOT requires exactly one child")
        return self


class DatabaseQuery(QueryModel):
    entity: Literal["projects", "jobs"] = "projects"
    skills: SkillExpression | None = Field(
        default=None,
        description="Boolean skills evaluated on one project, including for jobs. "
        "Terms match literal skill labels; related synonyms require a separate query.",
    )
    company: Term | None = None
    title: Term | None = Field(default=None, description="Project name or job title.")
    role: Term | None = Field(default=None, description="Matching project's role.")
    text: Term | None = Field(
        default=None, description="Literal text in the selected entity's career fields."
    )
    start_from: Month | None = None
    start_to: Month | None = None
    end_from: Month | None = None
    end_to: Month | None = None
    ongoing: bool | None = None
    kind: Literal["professional", "personal"] | None = None
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def bounded_query(self) -> Self:
        for lower, upper in (
            (self.start_from, self.start_to),
            (self.end_from, self.end_to),
        ):
            if lower and upper and lower > upper:
                raise ValueError("The beginning of a month range must precede its end")
        pending = [(self.skills, 1)] if self.skills else []
        count = 0
        while pending:
            expression, depth = pending.pop()
            count += 1
            if depth > 5 or count > 40:
                raise ValueError("Skill filters support at most 40 nodes and 5 levels")
            pending.extend((child, depth + 1) for child in expression.children)
        return self


class LinkedJob(BaseModel):
    id: int
    title: str = Field(max_length=200)
    company: str = Field(max_length=200)


class MatchingProject(BaseModel):
    id: int
    label: str = Field(max_length=200)
    matched_skills: list[Annotated[str, Field(max_length=100)]] = Field(
        default_factory=list, max_length=500
    )


class DatabaseRecord(BaseModel):
    id: int
    type: Literal["project", "job"]
    label: str
    start_month: Month | None = None
    end_month: Month | None = None
    ongoing: bool | None = None
    kind: Literal["professional", "personal"] | None = None
    role: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    linked_job: LinkedJob | None = None
    matching_project_count: int = Field(default=0, ge=0)
    matching_projects: list[MatchingProject] = Field(
        default_factory=list, max_length=20
    )
    text: str
    matched_skills: list[str]
    skills: list[dict] = Field(default_factory=list)


class DatabaseResult(BaseModel):
    entity: Literal["projects", "jobs"]
    total: int
    offset: int
    limit: int
    has_more: bool
    records: list[DatabaseRecord]
    source_refs: list[SourceRef]
    applied_criteria: dict
    skill_matches: dict[str, list[str]]
    counts: dict[str, int]


def skill_catalog(db: Session) -> list[str]:
    return list(db.scalars(select(Skill.keyword).order_by(func.lower(Skill.keyword))))


def matches_term(keyword: str, term: str) -> bool:
    value, needle = keyword.casefold(), term.casefold()
    if len(needle) <= 2:
        return bool(
            re.search(r"(?<![\w+#])" + re.escape(needle) + r"(?![\w+#])", value)
        )
    return needle in value


def skill_predicate(expression: SkillExpression, skills: list[Skill], matches: dict):
    if expression.op == "term":
        matching = [
            skill for skill in skills if matches_term(skill.keyword, expression.value)
        ]
        matches[expression.value] = [skill.keyword for skill in matching]
        return Project.skills.any(Skill.id.in_([skill.id for skill in matching]))
    children = [
        skill_predicate(child, skills, matches) for child in expression.children
    ]
    if expression.op == "not":
        return not_(children[0])
    return (and_ if expression.op == "and" else or_)(*children)


def project_predicates(query: DatabaseQuery, skills: list[Skill], matches: dict):
    conditions = []
    if query.skills:
        conditions.append(skill_predicate(query.skills, skills, matches))
    if query.role:
        conditions.append(Project.role.icontains(query.role, autoescape=True))
    if query.kind:
        conditions.append(
            Project.job_id.is_(None)
            if query.kind == "personal"
            else Project.job_id.is_not(None)
        )
    return conditions


def execute(db: Session, query: DatabaseQuery) -> DatabaseResult:
    skills = list(db.scalars(select(Skill).order_by(func.lower(Skill.keyword))))
    matches: dict[str, list[str]] = {}
    project_conditions = project_predicates(query, skills, matches)
    model = Project if query.entity == "projects" else Job
    conditions = list(project_conditions) if model is Project else []
    if model is Job and project_conditions:
        conditions.append(Job.projects.any(and_(*project_conditions)))
    if query.company:
        company = Job.company.icontains(query.company, autoescape=True)
        conditions.append(Project.job.has(company) if model is Project else company)
    if query.title:
        field = Project.name if model is Project else Job.title
        conditions.append(field.icontains(query.title, autoescape=True))
    if query.text:
        fields = (
            (
                Project.name,
                Project.role,
                Project.summary,
                Project.description,
                Project.outcomes,
            )
            if model is Project
            else (
                Job.title,
                Job.company,
                Job.location,
                Job.summary,
                Job.responsibilities,
                Job.achievements,
            )
        )
        conditions.append(
            or_(*(field.icontains(query.text, autoescape=True) for field in fields))
        )
    for field, lower, upper in (
        (model.start_month, query.start_from, query.start_to),
        (model.end_month, query.end_from, query.end_to),
    ):
        if lower:
            conditions.append(field >= lower)
        if upper:
            conditions.append(field <= upper)
    if query.ongoing is not None:
        conditions.append(model.ongoing.is_(query.ongoing))

    # Capture full membership and its count before slicing the displayed page.
    rows = db.execute(
        select(model, func.count().over())
        .where(*conditions)
        .order_by(model.start_month.desc().nulls_last(), model.id.desc())
    ).all()
    records = [row[0] for row in rows]
    total = rows[0][1] if rows else 0
    refs: list[SourceRef] = [(query.entity, record.id) for record in records]
    projects = (
        records
        if model is Project
        else list(
            db.scalars(
                select(Project)
                .where(
                    Project.job_id.in_([record.id for record in records])
                    if records
                    else false(),
                    *project_conditions,
                )
                .order_by(Project.start_month.desc().nulls_last(), Project.id.desc())
            )
        )
    )
    if model is Job:
        refs.extend(("projects", project.id) for project in projects)
    resolved_labels = {value for values in matches.values() for value in values}

    def matched_skills(projects):
        return sorted(
            {skill.keyword for project in projects for skill in project.skills}
            & resolved_labels,
            key=str.casefold,
        )

    page = []
    for record in records[query.offset : query.offset + query.limit]:
        linked = (
            [record]
            if model is Project
            else [project for project in projects if project.job_id == record.id]
        )
        text = source_text(record)
        if model is Job and project_conditions:
            text += "\n\nMatching project evidence:\n" + "\n\n".join(
                source_text(project) for project in linked
            )
        job = record.job if model is Project else record
        page.append(
            DatabaseRecord(
                id=record.id,
                type="project" if model is Project else "job",
                label=label(record),
                start_month=record.start_month,
                end_month=record.end_month,
                ongoing=record.ongoing,
                kind=record.kind if model is Project else None,
                role=record.role if model is Project else record.title,
                company=job.company if job else "",
                linked_job=LinkedJob(id=job.id, title=job.title, company=job.company)
                if model is Project and job
                else None,
                matching_project_count=len(linked) if model is Job else 0,
                matching_projects=[
                    MatchingProject(
                        id=project.id,
                        label=label(project),
                        matched_skills=matched_skills([project]),
                    )
                    for project in linked[:20]
                ]
                if model is Job
                else [],
                text=text,
                matched_skills=matched_skills(linked),
                skills=[
                    {"id": skill.id, "keyword": skill.keyword}
                    for skill in record.skills
                ]
                if model is Project
                else [],
            )
        )
    return DatabaseResult(
        entity=query.entity,
        total=total,
        offset=query.offset,
        limit=query.limit,
        has_more=query.offset + len(page) < total,
        records=page,
        source_refs=refs,
        applied_criteria=query.model_dump(
            exclude_none=True, exclude={"offset", "limit"}
        ),
        skill_matches=matches,
        counts={
            "projects": len(projects),
            "jobs": total
            if model is Job
            else len({project.job_id for project in projects if project.job_id}),
        },
    )
