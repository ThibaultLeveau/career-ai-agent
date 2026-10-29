"""The Representative selects views; only the server can populate their records."""

from sqlalchemy.orm import Session

from app.chat import components
from app.chat.query_schema import DatabaseRequest
from app.chat.schemas import Citation, DetailAction
from app.db import get_engine

RULES = """Select reusable career components with select_presentation. The catalog
contains the only allowed type/reference pairs. Never invent references or record data.
Use Project List or Job List for explicit lists and when several relevant records
help answer the question. Use cards for a specific project's or job's details.
Counts alone and aggregate rankings can use no components. Do not convert aggregate
groups into record lists. Keep exact and related matches distinct in introductions.
Every selection needs a short, natural AI introduction in the visitor's language,
grounded in the evidence. Describe why these records answer the question. Do not
repeat entire records or produce a second table: the interface supplies those fields.
For lists, describe the complete matching collection, not a displayed page. Never
write a page range such as 'showing 1–8' in the introduction: the interface controls
pagination and displays the current range. The total is the complete collection;
initially_visible is only the first page. Do not say all rows are visible at once.
If you select a Job Card, immediately follow it with its associated Project List
when the catalog provides one, with a separate introduction. These are ALL projects
in that job, regardless of the previous question's filters; say so when relevant.
Include all required_references (detail clicks) in order. Select at most four views.
Use the tool exactly once, returning an empty components array when prose suffices.
"""


def register(targets, query: DatabaseRequest, evidence, refs, handle, match_type):
    if query.operation == "query":
        primary = evidence.pop("primary_refs", [])
        page = evidence.pop("page_primary_refs", [])
        entity = query.query.entity
    else:
        entity = query.read.entity if query.operation == "read" else query.entity
        primary = [(kind, id) for kind, id in refs if kind == entity]
        page = [
            (entity, record["id"])
            for record in evidence.get("records", [])
            if not record.get("missing")
        ]
    if entity not in {"projects", "jobs"}:
        return
    ids = list(dict.fromkeys(id for kind, id in primary if kind == entity))
    if len(ids) > 10000:
        return
    prefix = entity[:-1]
    if query.operation != "read":
        # Aggregate queries without a primary record identity are not list candidates.
        if query.operation == "records" or primary:
            targets[handle] = components.Target(f"{prefix}_list", ids, match_type)
    labels = {
        record["id"]: record.get("label", "") for record in evidence.get("records", [])
    }
    for kind, id in page[:20]:
        if kind == entity:
            reference = f"{prefix}-{id}"
            if reference in targets and targets[reference].match_type == "exact":
                continue
            targets[reference] = components.Target(
                f"{prefix}_card", [id], match_type, labels.get(id, "")
            )


def catalog(targets: dict[str, components.Target]) -> list[dict]:
    with Session(get_engine()) as db:
        for reference, target in list(targets.items()):
            if target.type == "job_card":
                ids = components.associated_projects(db, target.ids[0])
                if ids and len(ids) <= 10000:
                    targets[f"{reference}-projects"] = components.Target(
                        "project_list",
                        ids,
                        "associated",
                        "All projects associated with this job",
                    )
    return [
        {
            "reference": reference,
            "type": target.type,
            "total": len(target.ids),
            "match_type": target.match_type,
            "label": target.label,
            **(
                {"associated_projects": f"{reference}-projects"}
                if f"{reference}-projects" in targets
                else {}
            ),
        }
        for reference, target in targets.items()
    ]


def validate(plan: components.Presentation, targets, required):
    references = [item.reference for item in plan.components]
    if len(references) != len(set(references)):
        raise ValueError("Select each component at most once.")
    if any(reference not in references for reference in required):
        raise ValueError("Include the required detail card.")
    for index, item in enumerate(plan.components):
        target = targets.get(item.reference)
        if target is None or target.type != item.type:
            raise ValueError(
                "Use only type/reference pairs from the component catalog."
            )
        if target.match_type == "associated" and (
            index == 0
            or references[index - 1] != item.reference.removesuffix("-projects")
        ):
            raise ValueError("Associated projects must follow their job card.")
        associated = f"{item.reference}-projects"
        if target.type == "job_card" and associated in targets:
            if index + 1 == len(references) or references[index + 1] != associated:
                raise ValueError(
                    "Follow each job card with its associated project list."
                )


def hydrate(plan: components.Presentation, targets, config):
    events, sources = [], []
    with Session(get_engine()) as db:
        for selection in plan.components:
            view = components.render(db, targets[selection.reference], config)
            events.append(
                components.ComponentEvent(
                    introduction=selection.introduction, component=view
                )
            )
            rows = (
                view.items if isinstance(view, components.ListPage) else [view.record]
            )
            for row in rows:
                project = isinstance(row, components.ProjectRow)
                kind = "project" if project else "job"
                sources.append(
                    Citation(
                        id=f"{kind}-{row.id}",
                        label=row.name if project else f"{row.title} — {row.company}",
                        source_type=kind,
                    )
                )
    return events, sources


def detail(action: DetailAction):
    scope = components.detail_scope(action)
    with Session(get_engine()) as db:
        view = components.card(db, scope.entity, scope.id)
        record = view.record.model_dump(exclude={"action"})
    kind = scope.entity[:-1]
    label = (
        record["name"]
        if kind == "project"
        else f"{record['title']} — {record['company']}"
    )
    reference = f"{kind}-{scope.id}"
    return (
        reference,
        components.Target(f"{kind}_card", [scope.id], label=label),
        {
            "kind": "database",
            "operation": "detail",
            "entity": scope.entity,
            "total": 1,
            "match_type": "exact",
            "records": [{"id": scope.id, "label": label, "text": str(record)}],
        },
    )
