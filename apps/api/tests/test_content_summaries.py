import asyncio
import os
from contextlib import nullcontext
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.admin.models import ProviderKey, RagConfiguration
from app.admin.schemas import Generation, RagSettings
from app.admin.security import cipher
from app.chat.database import DatabaseQuery, execute
from app.chat.providers import ChatError
from app.chat.query_schema import ReadRequest
from app.chat.resource_reader import render, snapshot
from app.content import summaries
from app.content.models import Job, Project
from app.content.schemas import JobInput, ProjectInput
from app.content.summaries import SummaryGeneration, generate_summary
from app.ingestion.models import IngestionJob, Source
from app.ingestion.service import source_text

database = pytest.mark.skipif(
    not os.environ.get("TEST_ADMIN_DB"),
    reason="Run scripts/check.sh for PostgreSQL tests",
)
PREPARED = SummaryGeneration(Generation(model="test-model"), "test-key")


@pytest.mark.parametrize(
    "schema,identity,fields",
    [
        (
            JobInput,
            {"title": "Engineer", "company": "Acme"},
            ["summary", "responsibilities", "achievements"],
        ),
        (
            ProjectInput,
            {"name": "Search"},
            ["summary", "description", "contribution", "outcomes"],
        ),
    ],
)
def test_markdown_whitespace_and_small_summary_limit(schema, identity, fields):
    markdown = "    indented code\n\nA **bold** sentence.  \nNext line.\n"
    values = schema(
        **identity, **dict.fromkeys(fields, markdown), small_summary="x" * 280
    )
    assert all(getattr(values, field) == markdown for field in fields)
    with pytest.raises(ValidationError):
        schema(**identity, small_summary="x" * 281)


def test_generation_uses_only_overview_and_retries_invalid_output(monkeypatch):
    complete = AsyncMock(side_effect=["**Not plain text**", "Built reliable search."])
    monkeypatch.setattr(summaries.providers, "complete", complete)
    overview = "    Search implementation\n\nBuilt reliable search."
    assert asyncio.run(generate_summary(overview, PREPARED)) == "Built reliable search."
    assert complete.await_count == 2
    first, second = complete.call_args_list
    assert first.args[:2] == (PREPARED.config, "test-key")
    assert "Search implementation" in first.args[2]
    assert "untrusted source content" in first.args[3]
    assert "previous attempt" in second.args[3]


@pytest.mark.parametrize(
    "output", ["x" * 281, "", "# Title", "<b>Unsafe</b>", "An *italic* result"]
)
def test_generation_rejects_repeated_invalid_output(monkeypatch, output):
    complete = AsyncMock(return_value=output)
    monkeypatch.setattr(summaries.providers, "complete", complete)
    with pytest.raises(HTTPException, match="valid short summary") as error:
        asyncio.run(generate_summary("Overview", PREPARED))
    assert error.value.status_code == 502 and complete.await_count == 2


def test_generation_handles_unavailable_provider_and_blank_overview(monkeypatch):
    complete = AsyncMock(side_effect=ChatError())
    monkeypatch.setattr(summaries.providers, "complete", complete)
    with pytest.raises(ValidationError):
        asyncio.run(generate_summary(" \n ", PREPARED))
    complete.assert_not_called()
    with pytest.raises(HTTPException, match="provider could not generate"):
        asyncio.run(generate_summary("Overview", PREPARED))
    assert complete.await_count == 1


def configure_generation(db):
    config = RagSettings()
    config.chat.model = "test-model"
    config.chat.max_output_tokens = 5096
    db.merge(RagConfiguration(id=1, configuration=config.model_dump()))
    db.merge(
        ProviderKey(
            provider="openai", encrypted_key=cipher().encrypt(b"test-key").decode()
        )
    )
    db.commit()


@database
def test_summary_endpoint_auth_validation_and_draft_only(client, db, monkeypatch):
    complete = AsyncMock(return_value="Built reliable search.")
    monkeypatch.setattr(summaries.providers, "complete", complete)
    path = "/admin/content/small-summary"
    assert client.post(path, json={"overview": "Search"}).status_code == 401
    client.post(
        "/admin/login",
        json={"username": "owner", "password": "initial-test-password"},
    )
    assert client.post(path, json={"overview": "Search"}).status_code == 422
    configure_generation(db)
    assert (
        client.post(
            path, json={"overview": "Search"}, headers={"Origin": "https://other.test"}
        ).status_code
        == 403
    )
    assert client.post(path, json={"overview": " \n "}).status_code == 422
    assert client.post(path, json={"overview": "x" * 8001}).status_code == 422
    response = client.post(path, json={"overview": "Built reliable search."})
    assert response.status_code == 200
    assert response.json() == {"small_summary": "Built reliable search."}
    assert response.headers["cache-control"] == "no-store"
    assert db.scalar(select(func.count()).select_from(Project)) == 0
    assert db.scalar(select(func.count()).select_from(IngestionJob)) == 0
    complete.assert_awaited_once()
    assert complete.call_args.args[0].max_output_tokens == 5096


@database
def test_markdown_contribution_and_list_summary_persistence(client, db):
    client.post(
        "/admin/login",
        json={"username": "owner", "password": "initial-test-password"},
    )
    contribution = "    authored code\n\nBuilt **hybrid retrieval**.  \n"
    payload = {
        "name": "Search",
        "summary": "    Overview indentation\n",
        "contribution": contribution,
        "small_summary": "Compact list summary",
    }
    response = client.post("/admin/projects", json=payload)
    assert response.status_code == 201
    record_id = response.json()["id"]
    assert response.json()["contribution"] == contribution
    assert response.json()["summary"] == payload["summary"]
    source = db.scalar(select(Source).where(Source.record_id == record_id))
    revision, content_hash = source.revision, source.content_hash
    record = db.get(Project, record_id)
    assert contribution in source_text(record)
    assert "Compact list summary" not in source_text(record)
    assert execute(db, DatabaseQuery(text="hybrid retrieval")).total == 1
    request = ReadRequest(entity="projects", ids=[record_id])
    result = render(request, snapshot(db, request))
    assert contribution in result["records"][0]["text"]
    assert "contribution" not in result["records"][0]

    payload["small_summary"] = "Revised compact list summary"
    response = client.put(f"/admin/projects/{record_id}", json=payload)
    assert response.status_code == 200
    assert response.json()["small_summary"] == payload["small_summary"]
    db.refresh(source)
    assert (source.revision, source.content_hash) == (revision, content_hash)
    assert db.scalar(select(func.count()).select_from(IngestionJob)) == 1
    payload["small_summary"] = "x" * 281
    assert client.put(f"/admin/projects/{record_id}", json=payload).status_code == 422


@database
def test_backfill_only_missing_summaries_and_preserves_concurrent_edits(
    db, monkeypatch
):
    configure_generation(db)
    job = Job(title="Engineer", company="Acme", summary="Built search")
    project = Project(name="Search", summary="Improved search")
    existing = Project(
        name="Saved", summary="Existing overview", small_summary="Manual"
    )
    blank = Project(name="Empty", summary=" \n ")
    db.add_all([job, project, existing, blank])
    db.commit()
    monkeypatch.setattr(summaries, "Session", lambda _engine: nullcontext(db))

    async def generate(overview, _prepared):
        if overview == "Improved search":
            project.small_summary = "Concurrent edit"
            db.commit()
        return "Generated summary"

    monkeypatch.setattr(summaries, "generate_summary", generate)
    assert asyncio.run(summaries.backfill(dry_run=True))["pending"] == 2
    result = asyncio.run(summaries.backfill())
    assert result == {"pending": 2, "generated": 1, "skipped": 1, "errors": []}
    db.expire_all()
    assert job.small_summary == "Generated summary"
    assert project.small_summary == "Concurrent edit"
    assert existing.small_summary == "Manual" and blank.small_summary == ""
    assert db.scalar(select(func.count()).select_from(IngestionJob)) == 0
