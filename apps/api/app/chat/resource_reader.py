import multiprocessing
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.query_catalog import FIELDS, MODELS
from app.chat.query_schema import ReadRequest
from app.content.models import Project
from app.ingestion.models import IngestionJob, Source
from app.ingestion.service import label, source_text
from app.ingestion.text import IngestionError, extract_pdf


def snapshot(db: Session, request: ReadRequest) -> list[dict]:
    model = MODELS[request.entity]
    found = {
        row.id: row
        for row in db.scalars(select(model).where(model.id.in_(request.ids)))
    }
    results = []
    for record_id in dict.fromkeys(request.ids):
        record = found.get(record_id)
        if record is None:
            results.append({"id": record_id, "missing": True})
            continue
        item = {name: getattr(record, name) for name in FIELDS[request.entity]}
        item["label"] = label(record)
        if request.entity == "projects":
            item["skills"] = [{"id": s.id, "keyword": s.keyword} for s in record.skills]
            item["job"] = (
                {
                    "id": record.job.id,
                    "title": record.job.title,
                    "company": record.job.company,
                }
                if record.job
                else None
            )
        if request.entity in {"skills", "jobs"}:
            projects = list(
                db.scalars(
                    select(Project)
                    .where(
                        Project.skills.any(id=record_id)
                        if request.entity == "skills"
                        else Project.job_id == record_id
                    )
                    .order_by(Project.id)
                )
            )
            item["projects"] = [
                {
                    "id": p.id,
                    "name": p.name,
                    "skills": [{"id": s.id, "keyword": s.keyword} for s in p.skills],
                }
                for p in projects
            ]
        if request.entity == "documents":
            cached = db.scalar(
                select(IngestionJob.plain_text)
                .join(Source, IngestionJob.source_id == Source.id)
                .where(
                    Source.source_type == "documents",
                    Source.record_id == record_id,
                    IngestionJob.revision == Source.revision,
                    IngestionJob.plain_text.is_not(None),
                )
                .order_by(IngestionJob.id.desc())
                .limit(1)
            )
            item["cached_text"] = cached
            item["pdf"] = (
                record.content
                if cached is None or request.page_start is not None
                else None
            )
        elif request.entity != "skills":
            item["text"] = source_text(record)
            # Large narratives are paged through text, not duplicated in metadata.
            for field in (
                "summary",
                "description",
                "contribution",
                "outcomes",
                "responsibilities",
                "achievements",
            ):
                item.pop(field, None)
        results.append(item)
    return results


def extract_in_process(content, connection):
    try:
        pages = extract_pdf(content)
        if sum(len(value) for _, value in pages) > 2000000:
            raise IngestionError(
                "Document text exceeds the 2-million-character reading limit"
            )
        connection.send((pages, None))
    except Exception as error:
        connection.send(
            (
                None,
                str(error)
                if isinstance(error, IngestionError)
                else "Document extraction failed",
            )
        )
    finally:
        connection.close()


def extract_bounded(content: bytes, timeout: float = 10):
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=extract_in_process, args=(content, sender), daemon=True
    )
    process.start()
    sender.close()
    try:
        if not receiver.poll(max(0, timeout)):
            raise ValueError("Document extraction exceeded the time limit")
        pages, error = receiver.recv()
        if error:
            raise ValueError(error)
        return pages
    except EOFError:
        raise ValueError("Document extraction could not complete") from None
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join()


def render(request: ReadRequest, snapshots: list[dict]) -> dict:
    records, refs, citations, limitations = [], set(), [], []
    remaining = request.max_chars
    deadline = monotonic() + 10
    for item in snapshots:
        if item.get("missing"):
            records.append(item)
            continue
        value = dict(item)
        page_start = page_end = None
        if request.entity == "documents":
            pdf = value.pop("pdf")
            text = value.pop("cached_text")
            if pdf is not None:
                try:
                    if monotonic() >= deadline:
                        raise ValueError("Document reading exceeded the time limit")
                    pages = extract_bounded(pdf, timeout=deadline - monotonic())
                except ValueError as error:
                    value["text_unavailable"] = str(error)
                    limitations.append(str(error))
                    pages = []
                if request.page_start is not None:
                    pages = [
                        (number, text)
                        for number, text in pages
                        if request.page_start <= number <= request.page_end
                    ]
                    if not pages and "text_unavailable" not in value:
                        value["text_unavailable"] = (
                            "No pages exist in the requested range"
                        )
                if pages:
                    page_start, page_end = pages[0][0], pages[-1][0]
                text = "\n\n".join(f"Page {number}:\n{text}" for number, text in pages)
            value["text"] = text or ""
        if "text" in value:
            full = value["text"]
            value["text"] = full[request.offset : request.offset + remaining]
            remaining -= len(value["text"])
            end = request.offset + len(value["text"])
            value["text_complete"] = (
                end >= len(full) and "text_unavailable" not in value
            )
            value["next_offset"] = end if end < len(full) else None
            value["text_length"] = len(full)
        if request.entity != "skills":
            refs.add((request.entity, item["id"]))
            citations.append(
                {
                    "id": f"{request.entity[:-1]}-{item['id']}",
                    "label": item["label"],
                    "source_type": request.entity[:-1],
                    "page_start": page_start,
                    "page_end": page_end,
                }
            )
        if request.entity in {"skills", "jobs"}:
            refs.update(("projects", p["id"]) for p in item["projects"])
            citations.extend(
                {
                    "id": f"project-{p['id']}",
                    "label": p["name"],
                    "source_type": "project",
                }
                for p in item["projects"]
            )
        records.append(value)
    return {
        "entity": request.entity,
        "records": records,
        "total": len(records),
        "complete": all(
            not r.get("missing") and r.get("text_complete", True) for r in records
        ),
        "source_refs": sorted(refs),
        "citations": citations,
        "limitations": limitations,
        "applied_criteria": request.model_dump(exclude_none=True),
    }
