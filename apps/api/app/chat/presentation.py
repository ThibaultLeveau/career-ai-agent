"""The Representative selects views; only the server can populate their records."""

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat import components
from app.chat.query_schema import DatabaseRequest
from app.chat.schemas import Citation, DetailAction
from app.content.models import Job, Project
from app.db import get_engine

RULES = """Select reusable career components with select_presentation. The catalog
contains the only allowed type/reference pairs. Never invent references or record data.
Use Project List or Job List for explicit lists and when several relevant records
help answer the question. Use cards for a specific project's or job's details.
When discussing only selected examples, set record_ids to exactly those verified
IDs in the order you discuss them. Use only IDs belonging to that list reference;
never show a whole research result when your answer describes a smaller selection.
Omit record_ids to show the complete verified result, as for an exhaustive list.
Never provide record_ids for cards or associated project lists. Keep selections
from exact and related result sets separate. Record labels are navigation only;
use the research evidence to decide relevance.
Counts alone and aggregate rankings can use no components. Do not convert aggregate
groups into record lists. Keep exact and related matches distinct in introductions.
Every selection needs a short, natural AI introduction in the visitor's language,
grounded in the evidence. Describe why these records answer the question. Do not
repeat entire records or produce a second table: the interface supplies those fields.
For lists, the introduction describes the collection chosen by record_ids across
all its pages; when record_ids is omitted, it describes the full verified target.
The catalog total counts that target before selection, not the chosen subset.
initially_visible describes its initial page before selection. Never write a page
range such as 'showing 1–8': the interface controls pagination and its current range.
Do not say all rows are visible at once or call selected examples exhaustive.
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


def record_labels(db: Session, entity: str, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    model = Project if entity == "projects" else Job
    label = model.name if model is Project else model.title + " — " + model.company
    labels = dict(db.execute(select(model.id, label).where(model.id.in_(ids))).all())
    return [{"id": id, "label": labels[id]} for id in ids if id in labels]


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
                        job_id=target.ids[0],
                    )
    options = []
    for reference, target in targets.items():
        option = {
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
        if target.type.endswith("_list"):
            labels = {
                item.ids[0]: item.label
                for item in targets.values()
                if item.type == target.type.replace("_list", "_card") and item.label
            }
            option["record_ids"] = target.ids
            option["records"] = [
                {"id": id, "label": labels[id]}
                for id in target.ids[:100]
                if id in labels
            ]
        options.append(option)
    return options


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
        if item.record_ids is not None:
            if target.type.endswith("_card") or target.match_type == "associated":
                raise ValueError("Do not narrow cards or associated project lists.")
            if len(item.record_ids) != len(set(item.record_ids)):
                raise ValueError("Select each record at most once.")
            if not item.record_ids or not set(item.record_ids).issubset(target.ids):
                raise ValueError("Select only verified IDs from this list reference.")
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
            target = targets[selection.reference]
            if selection.record_ids is not None:
                target = replace(target, ids=selection.record_ids)
            view = components.render(db, target, config)
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


def context(events: list[components.ComponentEvent]) -> list[dict]:
    result = []
    with Session(get_engine()) as db:
        for event in events:
            view = event.component
            if isinstance(view, components.ListPage):
                scope = components.unseal(view.token, components.ListScope)
                records = record_labels(db, scope.entity, scope.ids[:100])
                total = view.total
            else:
                record = view.record
                records = [
                    {
                        "id": record.id,
                        "label": record.name
                        if isinstance(record, components.ProjectRow)
                        else f"{record.title} — {record.company}",
                    }
                ]
                total = 1
            result.append(
                {
                    "type": view.type,
                    "introduction": event.introduction,
                    "selected_total": total,
                    "selected_records": records,
                    "records_complete": len(records) == total,
                }
            )
    return result


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
