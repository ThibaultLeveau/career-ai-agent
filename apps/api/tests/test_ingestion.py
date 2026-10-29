import os
from contextlib import nullcontext
from datetime import timedelta
from io import BytesIO
from unittest.mock import Mock

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import func, select

from app.content.models import Job, Project, Skill
from app.ingestion import worker
from app.ingestion.models import Chunk, IngestionJob, Source
from app.ingestion.provider import embed, retry_delay
from app.ingestion.service import enqueue, now, source_text
from app.ingestion.text import IngestionError, chunk_text, extract_pdf, tokenizer

database = pytest.mark.skipif(
    not os.environ.get("TEST_ADMIN_DB"), reason="Requires PostgreSQL"
)


def pdf_bytes(text="Software engineer in Paris", encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_chunking_overlap_token_limits_and_unicode():
    value = "Bonjour 👩🏽‍💻 世界 café Python. " * 100
    plain, chunks = chunk_text([(1, value), (2, "Second page")], 100, 15)
    assert plain == value + "\n\nSecond page"
    assert len(chunks) > 2
    assert all(chunk.text in plain and "�" not in chunk.text for chunk in chunks)
    assert all(chunk.token_count <= 100 for chunk in chunks)
    assert chunks[0].page_start == 1 and chunks[-1].page_end == 2
    _, chunks = chunk_text([(None, " word" * 250)], 100, 20)
    assert (
        tokenizer().encode(chunks[0].text)[-20:]
        == tokenizer().encode(chunks[1].text)[:20]
    )
    with pytest.raises(ValueError):
        chunk_text([(None, "test")], 100, 100)


def test_pdf_extraction_errors_and_pages():
    assert "Software engineer" in extract_pdf(pdf_bytes())[0][1]
    for content, message in [
        (b"%PDF-broken", "valid text PDF"),
        (pdf_bytes(""), "OCR"),
        (pdf_bytes(encrypted=True), "encrypted"),
    ]:
        with pytest.raises(IngestionError, match=message):
            extract_pdf(content)


def mock_provider(monkeypatch, response):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.return_value = response
    monkeypatch.setattr(
        "app.ingestion.provider.httpx.Client", Mock(return_value=client)
    )


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (429, None, True),
        (503, None, True),
        (429, "insufficient_quota", False),
        (401, None, False),
        (400, None, False),
    ],
)
def test_provider_retry_classification_and_sanitized_errors(
    monkeypatch, status, code, retryable
):
    mock_provider(
        monkeypatch,
        httpx.Response(
            status,
            json={"error": {"code": code, "message": "private secret"}},
            headers={"Retry-After": "20"},
        ),
    )
    with pytest.raises(IngestionError) as caught:
        embed(["hello"], {"model": "text-embedding-3-small", "dimensions": 3}, "secret")
    assert caught.value.retryable == retryable
    assert "private" not in str(caught.value)
    if retryable:
        assert caught.value.delay == 20


def test_provider_order_and_invalid_vectors(monkeypatch):
    config = {"model": "text-embedding-3-small", "dimensions": 3}
    data = [{"index": 1, "embedding": [1, 2, 3]}, {"index": 0, "embedding": [4, 5, 6]}]
    mock_provider(monkeypatch, httpx.Response(200, json={"data": data}))
    assert embed(["a", "b"], config, "secret") == [[4, 5, 6], [1, 2, 3]]
    for invalid in [
        [],
        [{"index": 0, "embedding": [1]}],
        [{"index": 0, "embedding": [True, 1, 2]}],
    ]:
        mock_provider(monkeypatch, httpx.Response(200, json={"data": invalid}))
        with pytest.raises(IngestionError, match="invalid embeddings"):
            embed(["a"], config, "secret")
    assert retry_delay("invalid") == 0
    assert retry_delay("inf") == 0


@pytest.fixture
def pipeline(client, db, monkeypatch):
    client.post(
        "/admin/login", json={"username": "owner", "password": "initial-test-password"}
    )
    config = client.get("/admin/settings").json()
    config["embeddings"]["dimensions"] = 3
    assert client.put("/admin/settings", json=config).status_code == 200
    client.put("/admin/providers/openai", json={"key": "mock-key"})
    monkeypatch.setattr(worker, "session", lambda: nullcontext(db))
    monkeypatch.setattr(
        worker,
        "embed",
        lambda texts, config, key: [[0.1] * config["dimensions"] for _ in texts],
    )
    return client


def process_next(db):
    claimed = worker.claim(db)
    assert claimed
    try:
        worker.process(*claimed)
    except IngestionError as error:
        worker.failure(*claimed, error)
    db.expire_all()
    return db.get(IngestionJob, claimed[0])


@database
def test_async_save_atomic_publish_and_stale_settings(pipeline, db):
    client = pipeline
    response = client.post("/admin/jobs", json={"title": "Engineer", "company": "Acme"})
    record = response.json()
    assert response.status_code == 201 and record["ingestion"]["status"] == "queued"
    job = process_next(db)
    assert job.status == "succeeded" and job.plain_text.startswith("Title: Engineer")
    source = db.get(Source, job.source_id)
    assert source.active_job_id == job.id
    assert len(db.scalar(select(Chunk)).embedding) == 3
    config = client.get("/admin/settings").json()
    config["ingestion"]["max_retries"] = 0
    client.patch("/admin/settings", json={"ingestion": config["ingestion"]})
    assert (
        client.get(f"/admin/jobs/{record['id']}").json()["ingestion"]["status"]
        == "succeeded"
    )
    config["ingestion"]["chunk_overlap"] = 50
    client.patch("/admin/settings", json={"ingestion": config["ingestion"]})
    assert (
        client.get(f"/admin/jobs/{record['id']}").json()["ingestion"]["status"]
        == "outdated"
    )
    assert db.scalar(select(func.count()).select_from(IngestionJob)) == 1
    assert client.get("/admin/settings").json()["embeddings"]["dimensions"] == 3


@database
def test_manual_bulk_exclusion_and_history_on_delete(pipeline, db):
    client = pipeline
    item = client.post("/admin/projects", json={"name": "Python"}).json()
    path = f"/admin/ingestion/projects/{item['id']}/reingest"
    conflict = client.post(path)
    assert (
        conflict.status_code == 409
        and f"#{item['ingestion']['job_id']}" in conflict.text
    )
    result = client.post(
        "/admin/ingestion/reingest", json={"source_types": ["projects", "projects"]}
    )
    assert result.status_code == 202 and result.json()["skipped"] == 1
    job = process_next(db)
    assert client.post(path).status_code == 202
    client.delete(f"/admin/projects/{item['id']}")
    assert db.scalar(select(func.count()).select_from(Chunk)) == 0
    history = client.get("/admin/ingestion/jobs?source_type=projects&limit=1").json()
    assert history["total"] == 2
    assert history["items"][0]["status"] == "cancelled"
    assert history["items"][0]["source_deleted"]
    assert client.get(f"/admin/ingestion/jobs/{job.id}/logs").json()
    assert client.get("/admin/ingestion/jobs?limit=10000").status_code == 422


@database
def test_edit_coalescing_and_related_project_changes(pipeline, db):
    client = pipeline
    skill = client.post("/admin/skills", json={"keyword": "Python"}).json()
    project = client.post(
        "/admin/projects", json={"name": "Search", "skill_ids": [skill["id"]]}
    ).json()
    client.put(f"/admin/skills/{skill['id']}", json={"keyword": "Python 3"})
    assert "ingestion" not in skill
    assert db.scalar(select(func.count()).select_from(IngestionJob)) == 1
    assert process_next(db).status == "superseded"
    latest = process_next(db)
    assert latest.status == "succeeded" and "Python 3" in latest.plain_text
    client.delete(f"/admin/skills/{skill['id']}")
    assert process_next(db).status == "succeeded"
    source = db.scalar(
        select(Source).where(
            Source.source_type == "projects", Source.record_id == project["id"]
        )
    )
    assert "Python" not in db.get(IngestionJob, source.active_job_id).plain_text


@database
def test_retries_checkpoint_and_previous_embeddings_survive(pipeline, db, monkeypatch):
    client = pipeline
    item = client.post(
        "/admin/projects", json={"name": "Long project", "description": "word " * 1500}
    ).json()
    original = process_next(db)
    assert original.status == "succeeded"
    client.post(f"/admin/ingestion/projects/{item['id']}/reingest")
    monkeypatch.setattr(
        worker,
        "embed",
        Mock(side_effect=IngestionError("Temporary rate limit", True, 30)),
    )
    job = process_next(db)
    assert job.status == "retrying" and job.retries == 1
    assert job.available_at > now() + timedelta(seconds=29)
    assert db.get(Source, job.source_id).active_job_id == original.id
    for count in range(2, 5):
        job.available_at = now() - timedelta(seconds=1)
        db.commit()
        job = process_next(db)
        assert job.status == ("failed" if count == 4 else "retrying")
    assert db.get(Source, job.source_id).active_job_id == original.id
    assert (
        db.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.job_id == original.id)
        )
        > 0
    )


@database
def test_worker_recovery_fences_old_owner(pipeline, db):
    pipeline.post("/admin/projects", json={"name": "PostgreSQL"})
    first = worker.claim(db)
    assert worker.claim(db) is None
    job = db.get(IngestionJob, first[0])
    job.lease_until = now() - timedelta(seconds=1)
    db.commit()
    second = worker.claim(db)
    assert second[0] == first[0] and second[1] != first[1]
    worker.process(*first)
    assert db.scalar(select(func.count()).select_from(Chunk)) == 0
    worker.process(*second)
    db.refresh(job)
    assert job.status == "succeeded" and job.retries == 1


@database
def test_content_change_during_provider_call_cannot_publish(pipeline, db, monkeypatch):
    project = Project(name="Before")
    db.add(project)
    enqueue(db, "projects", project)
    db.commit()
    claimed = worker.claim(db)

    def change(texts, config, key):
        project.name = "After"
        enqueue(db, "projects", project)
        db.commit()
        return [[0.1] * 3 for _ in texts]

    monkeypatch.setattr(worker, "embed", change)
    worker.process(*claimed)
    db.expire_all()
    assert db.get(IngestionJob, claimed[0]).status == "superseded"
    assert db.scalar(select(Source)).active_job_id is None
    assert db.scalar(select(func.count()).select_from(IngestionJob)) == 2


@database
def test_ingestion_authentication_and_origin(client):
    assert client.get("/admin/overview").status_code == 401
    assert client.get("/admin/ingestion/jobs").status_code == 401
    assert client.get("/admin/ingestion/status?source_type=jobs").status_code == 401
    client.post(
        "/admin/login", json={"username": "owner", "password": "initial-test-password"}
    )
    assert (
        client.post(
            "/admin/ingestion/reingest",
            json={"source_types": ["jobs"]},
            headers={"Origin": "https://other.test"},
        ).status_code
        == 403
    )


@database
def test_document_ingestion_and_model_dimension_change(pipeline, db):
    client = pipeline
    response = client.post(
        "/admin/documents",
        data={"title": "Resume"},
        files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201
    job = process_next(db)
    assert job.status == "succeeded" and "Software engineer" in job.plain_text
    assert db.scalar(select(Chunk).where(Chunk.job_id == job.id)).page_start == 1
    new_model = {
        "provider": "openai",
        "model": "text-embedding-3-large",
        "dimensions": 3072,
    }
    client.patch("/admin/settings", json={"embeddings": new_model})
    assert client.get("/admin/documents").json()[0]["ingestion"]["status"] == "outdated"
    client.post(f"/admin/ingestion/documents/{response.json()['id']}/reingest")
    replacement = process_next(db)
    assert replacement.status == "succeeded"
    assert (
        len(db.scalar(select(Chunk).where(Chunk.job_id == replacement.id)).embedding)
        == 3072
    )
    assert (
        db.scalar(select(func.count()).select_from(Chunk).where(Chunk.job_id == job.id))
        == 0
    )


@database
def test_concurrent_enqueue_and_claim_use_database_exclusion():
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from app.db import get_engine

    engine = get_engine()
    with Session(engine) as db:
        project = Project(name=f"concurrency-{uuid4()}")
        db.add(project)
        db.commit()
        record_id = project.id
    try:

        def submit(_):
            with Session(engine) as db:
                _, created = enqueue(
                    db, "projects", db.get(Project, record_id), force=True
                )
                db.commit()
                return created

        def claim_one(_):
            with Session(engine) as db:
                return worker.claim(db)

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(submit, range(2))) == [False, True]
            claims = list(pool.map(claim_one, range(2)))
            assert sum(claim is not None for claim in claims) == 1
    finally:
        with Session(engine) as db:
            db.execute(
                delete(IngestionJob).where(
                    IngestionJob.source_type == "projects",
                    IngestionJob.record_id == record_id,
                )
            )
            db.execute(
                delete(Source).where(
                    Source.source_type == "projects", Source.record_id == record_id
                )
            )
            db.execute(delete(Project).where(Project.id == record_id))
            db.commit()


@database
def test_retry_resumes_after_completed_batch(pipeline, db, monkeypatch):
    config = pipeline.get("/admin/settings").json()["ingestion"]
    config.update(chunk_size=100, chunk_overlap=10)
    pipeline.patch("/admin/settings", json={"ingestion": config})
    pipeline.post(
        "/admin/projects",
        json={
            "name": "Batch checkpoints",
            "summary": "alpha " * 1200,
            "description": "bravo " * 1200,
            "outcomes": "charlie " * 900,
        },
    )
    calls = []

    def partial(texts, config, key):
        calls.append(texts)
        if len(calls) == 2:
            raise IngestionError("Temporary failure", True)
        return [[0.2] * 3 for _ in texts]

    monkeypatch.setattr(worker, "embed", partial)
    job = process_next(db)
    assert job.status == "retrying" and job.completed_chunks == 32
    first_batch = list(
        db.scalars(
            select(Chunk).where(Chunk.job_id == job.id, Chunk.embedding.is_not(None))
        )
    )
    assert len(first_batch) == 32
    job.available_at = now() - timedelta(seconds=1)
    db.commit()
    job = process_next(db)
    assert job.status == "succeeded"
    assert calls[2] == calls[1]
    assert len(calls) == 3


@database
def test_skills_are_keywords_only_and_rejected_by_enqueue(pipeline, db):
    skill = pipeline.post("/admin/skills", json={"keyword": "Python"}).json()
    assert "ingestion" not in skill
    assert pipeline.get("/admin/skills").json() == [skill]
    assert db.scalar(select(func.count()).select_from(IngestionJob)) == 0
    assert db.scalar(select(func.count()).select_from(Source)) == 0
    assert (
        pipeline.post(f"/admin/ingestion/skills/{skill['id']}/reingest").status_code
        == 422
    )
    assert (
        pipeline.post(
            "/admin/ingestion/reingest", json={"source_types": ["skills"]}
        ).status_code
        == 422
    )
    assert pipeline.get("/admin/ingestion/status?source_type=skills").status_code == 422
    with pytest.raises(ValueError, match="disabled"):
        enqueue(db, "skills", db.get(Skill, skill["id"]))


@database
def test_complete_documents_are_combined_before_chunking(pipeline, db):
    client = pipeline
    job_fields = {
        "title": "Engineer",
        "company": "Acme",
        "location": "Paris",
        "start_month": "2024-01",
        "end_month": "2025-06",
        "summary": "Summary marker",
        "responsibilities": "Responsibility marker",
        "achievements": "Achievement marker",
    }
    job = client.post("/admin/jobs", json=job_fields).json()
    skill = client.post("/admin/skills", json={"keyword": "Python"}).json()
    other = client.post("/admin/skills", json={"keyword": "Aardvark"}).json()
    project_fields = {
        "name": "Search",
        "role": "Lead",
        "start_month": "2025-07",
        "ongoing": True,
        "summary": "Overview marker",
        "description": "Description marker",
        "contribution": "Contribution marker",
        "outcomes": "Outcomes marker",
        "website_url": "https://example.com",
        "repository_url": "https://example.com/repo",
        "job_id": job["id"],
        "skill_ids": [skill["id"], other["id"]],
    }
    project = client.post("/admin/projects", json=project_fields).json()
    assert all("ingestion" not in keyword for keyword in project["skills"])
    job_run, project_run = process_next(db), process_next(db)
    assert all(value in job_run.plain_text for value in job_fields.values())
    assert all(
        value in project_run.plain_text
        for value in project_fields.values()
        if isinstance(value, str)
    )
    assert "Skills: Aardvark, Python" in project_run.plain_text
    assert "Job: Engineer at Acme" in project_run.plain_text
    assert (
        "Kind: professional" in project_run.plain_text
        and "End: Present" in project_run.plain_text
    )
    record = db.get(Project, project["id"])
    record.summary = " word" * 80
    record.description = " description" * 80
    plain, chunks = chunk_text([(None, source_text(record))], 100, 20)
    assert (
        plain.index("Summary:") < plain.index("Description:") < plain.index("Skills:")
    )
    assert any(
        " word" in chunk.text and "Description:" in chunk.text for chunk in chunks
    )
    assert (
        tokenizer().encode(chunks[0].text)[-20:]
        == tokenizer().encode(chunks[1].text)[:20]
    )
    client.put(
        f"/admin/jobs/{job['id']}", json={**job_fields, "title": "Principal engineer"}
    )
    assert process_next(db).status == "succeeded"
    assert "Job: Principal engineer at Acme" in process_next(db).plain_text


@database
def test_overview_counts_current_items_and_stale_settings(pipeline, db):
    client = pipeline
    client.post("/admin/skills", json={"keyword": "Python"})
    item = client.post(
        "/admin/jobs", json={"title": "Engineer", "company": "Acme"}
    ).json()

    def counts():
        return client.get("/admin/overview").json()

    assert counts() == {
        "active": True,
        "counts": {"jobs": 1, "projects": 0, "skills": 1, "documents": 0},
        "ingestion": {"pending": 1, "ongoing": 0, "failed": 0, "successful": 0},
    }
    claimed = worker.claim(db)
    assert counts()["ingestion"]["ongoing"] == 1
    worker.failure(*claimed, IngestionError("Temporary", True))
    assert counts()["ingestion"]["ongoing"] == 1
    run = db.get(IngestionJob, claimed[0])
    run.available_at = now() - timedelta(seconds=1)
    db.commit()
    assert process_next(db).status == "succeeded"
    assert counts()["ingestion"]["successful"] == 1
    client.post(f"/admin/ingestion/jobs/{item['id']}/reingest")
    claimed = worker.claim(db)
    worker.failure(*claimed, IngestionError("Permanent"))
    assert counts()["ingestion"]["failed"] == 1
    client.post(f"/admin/ingestion/jobs/{item['id']}/reingest")
    process_next(db)
    assert counts()["ingestion"]["successful"] == 1
    config = client.get("/admin/settings").json()["ingestion"]
    config["chunk_overlap"] = 80
    client.patch("/admin/settings", json={"ingestion": config})
    assert counts()["ingestion"]["pending"] == 1
    client.delete(f"/admin/jobs/{item['id']}")
    assert sum(counts()["ingestion"].values()) == 0
    assert client.get("/admin/ingestion/jobs").json()["total"] == 3
    db.add(Job(title="Never queued", company="Acme"))
    db.commit()
    assert counts()["ingestion"]["pending"] == 1


@database
def test_retirement_migration_preserves_skills_and_history(pipeline, db):
    import importlib.util

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from app.ingestion.models import Event
    from app.ingestion.service import fingerprint, settings

    skill = Skill(keyword="Legacy")
    db.add(skill)
    db.flush()
    project = Project(name="Uses legacy skill", skills=[skill])
    db.add(project)
    source = Source(
        source_type="skills", record_id=skill.id, revision=1, content_hash="a" * 64
    )
    db.add(source)
    db.flush()
    config = settings(db).model_dump()
    run = IngestionJob(
        source_id=source.id,
        source_type="skills",
        record_id=skill.id,
        label=skill.keyword,
        revision=1,
        trigger="save",
        status="running",
        stage="embedding",
        settings=config,
        fingerprint=fingerprint(config),
        plain_text="Legacy",
        created_at=now(),
        available_at=now(),
        owner="old-worker",
        lease_until=now() + timedelta(seconds=120),
    )
    db.add(run)
    db.flush()
    source.active_job_id = run.id
    db.add(
        Chunk(
            job_id=run.id, position=0, text="Legacy", token_count=1, embedding=[0.1] * 3
        )
    )
    db.commit()
    spec = importlib.util.spec_from_file_location(
        "retire", "migrations/versions/0005_retire_skill_ingestion.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with Operations.context(MigrationContext.configure(db.connection())):
        migration.upgrade()
    db.expire_all()
    assert db.get(Skill, skill.id).keyword == "Legacy"
    assert db.get(Project, project.id).skills[0].id == skill.id
    assert run.status == "cancelled" and run.owner is None and run.plain_text is None
    assert source.active_job_id is None
    assert db.scalar(select(func.count()).select_from(Chunk)) == 0
    assert db.scalar(select(Event).where(Event.job_id == run.id))
    history = pipeline.get("/admin/ingestion/jobs?source_type=skills").json()
    assert history["total"] == 1 and not history["items"][0]["source_deleted"]
    assert worker.claim(db) is None
    assert pipeline.get("/admin/overview").json()["ingestion"]["pending"] == 1
