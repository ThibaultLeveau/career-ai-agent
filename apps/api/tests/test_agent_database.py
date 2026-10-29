import asyncio
import os

import pytest
from pydantic import ValidationError

from app.admin.schemas import RagSettings
from app.chat import agents, database, retrieval, service
from app.chat.schemas import ChatRequest
from app.content.models import Job, Project, Skill
from app.ingestion.models import Chunk, IngestionJob, Source
from app.ingestion.service import now

requires_database = pytest.mark.skipif(
    not os.environ.get("TEST_ADMIN_DB"), reason="Requires PostgreSQL"
)


def term(value):
    return {"op": "term", "value": value}


def expression(op, *values):
    return {"op": op, "children": list(values)}


@pytest.mark.parametrize(
    ("keyword", "query", "expected"),
    [
        ("Python", "python", True),
        ("Advanced Python", "PYTHON", True),
        ("Agentic AI", "AI", True),
        ("OpenAI", "AI", False),
        ("LLMs", "AI", False),
        ("C++", "C", False),
        ("C#", "C", False),
        ("C", "C", True),
        ("SQL", "%", False),
        ("SQL_analytics", "_", False),
    ],
)
def test_skill_terms_are_literal_and_short_terms_use_boundaries(
    keyword, query, expected
):
    assert database.matches_term(keyword, query) is expected


def test_query_rejects_invalid_filters_and_unbounded_expression():
    for value in (
        {"limit": 21},
        {"offset": -1},
        {"sql": "DROP TABLE skill"},
        {"start_from": "2026-13"},
        {"start_from": "2026-10", "start_to": "2025-01"},
        {"skills": expression("not", term("AI"), term("PHP"))},
        {"skills": expression("and")},
        {"skills": {"value": ""}},
    ):
        with pytest.raises(ValidationError):
            database.DatabaseQuery.model_validate(value)
    nested = term("Python")
    for _ in range(5):
        nested = expression("not", nested)
    with pytest.raises(ValidationError):
        database.DatabaseQuery(skills=nested)


@pytest.fixture
def career(db):
    skills = {
        keyword: Skill(keyword=keyword)
        for keyword in (
            "Python",
            "Python data",
            "Agentic AI",
            "PHP",
            "OpenAI",
            "LLMs",
            "RAG",
        )
    }
    first = Job(title="Backend engineer", company="Acme", start_month="2020-01")
    second = Job(title="Team lead", company="Beta", start_month="2025-01")
    db.add_all([first, second, *skills.values()])
    db.flush()
    projects = []
    for index in range(7):
        projects.append(
            Project(
                name=f"Python {index}",
                start_month=f"{2020 + index}-01",
                role="Engineer",
                skills=[skills["Python"]]
                + ([skills["Python data"]] if index == 0 else []),
                job_id=first.id if index < 2 else None,
                ongoing=index == 6,
                description="Improved capacity 50%"
                if index == 0
                else "Software delivery",
            )
        )
    ai = Project(name="AI only", job_id=first.id, skills=[skills["Agentic AI"]])
    php = Project(name="PHP only", job_id=first.id, skills=[skills["PHP"]])
    both = Project(
        name="Combined", job_id=second.id, skills=[skills["Agentic AI"], skills["PHP"]]
    )
    unrelated = Project(name="OpenAI library", skills=[skills["OpenAI"]])
    db.add_all([*projects, ai, php, both, unrelated])
    db.commit()
    return first, second, projects, ai, php, both, unrelated


@requires_database
def test_boolean_skills_require_one_project_and_jobs_are_distinct(db, career):
    first, second, _, ai, php, both, unrelated = career
    combined = expression("and", term("AI"), term("PHP"))
    result = database.execute(db, database.DatabaseQuery(skills=combined))
    assert result.total == 1
    assert [record.id for record in result.records] == [both.id]
    assert result.skill_matches == {"AI": ["Agentic AI"], "PHP": ["PHP"]}
    assert result.records[0].matched_skills == ["Agentic AI", "PHP"]
    jobs = database.execute(db, database.DatabaseQuery(entity="jobs", skills=combined))
    assert jobs.total == 1 and jobs.records[0].id == second.id
    assert set(jobs.source_refs) == {("jobs", second.id), ("projects", both.id)}
    assert "Combined" in jobs.records[0].text
    assert "AI only" not in jobs.records[0].text
    either = database.execute(
        db, database.DatabaseQuery(skills=expression("or", term("AI"), term("PHP")))
    )
    assert {record.id for record in either.records} == {ai.id, php.id, both.id}
    assert unrelated.id not in {record.id for record in either.records}
    excluded = database.execute(
        db,
        database.DatabaseQuery(
            skills=expression("and", term("PHP"), expression("not", term("AI")))
        ),
    )
    assert excluded.total == 1 and excluded.records[0].id == php.id
    jobs = database.execute(
        db, database.DatabaseQuery(entity="jobs", skills=term("Python"))
    )
    assert jobs.total == 1 and jobs.records[0].id == first.id
    assert jobs.counts == {"projects": 2, "jobs": 1}


@requires_database
def test_count_and_complete_scope_are_independent_of_displayed_page(db, career):
    _, _, projects, *_ = career
    query = database.DatabaseQuery(skills=term("python"))
    first = database.execute(db, query)
    assert first.total == 7 and len(first.records) == 5 and first.has_more
    assert [record.id for record in first.records] == [
        project.id for project in reversed(projects[2:])
    ]
    assert len(first.source_refs) == 7
    assert first.counts == {"projects": 7, "jobs": 1}
    second = database.execute(db, query.model_copy(update={"offset": 5}))
    assert second.total == 7 and len(second.records) == 2 and not second.has_more
    assert first.source_refs == second.source_refs
    assert not {record.id for record in first.records} & {
        record.id for record in second.records
    }
    missing = database.execute(db, database.DatabaseQuery(skills=term("nonexistent")))
    assert missing.total == 0 and missing.source_refs == [] and missing.records == []
    assert database.skill_catalog(db) == sorted(
        database.skill_catalog(db), key=str.casefold
    )


@requires_database
def test_structured_filters_are_literal_and_use_current_records(db, career):
    _, _, projects, *_ = career
    result = database.execute(
        db,
        database.DatabaseQuery(
            company="ACME", role="engineer", start_from="2021-01", kind="professional"
        ),
    )
    assert result.total == 1 and result.records[0].id == projects[1].id
    result = database.execute(db, database.DatabaseQuery(text="%"))
    assert result.total == 1 and result.records[0].id == projects[0].id
    assert database.execute(db, database.DatabaseQuery(company="%")).total == 0
    result = database.execute(db, database.DatabaseQuery(ongoing=True, title="PYTHON"))
    assert result.total == 1 and result.records[0].id == projects[6].id
    projects[6].skills = []
    db.flush()
    assert (
        database.execute(db, database.DatabaseQuery(skills=term("python"))).total == 6
    )


@requires_database
def test_current_metadata_survives_long_narrative_evidence_truncation(db, career):
    first, _, projects, *_ = career
    project = projects[6]
    project.job = first
    project.summary = "Long early narrative. " * 2000
    first.summary = "Long job narrative. " * 2000
    db.flush()
    result = database.execute(db, database.DatabaseQuery(title=project.name))
    full = result.records[0].text
    assert "End: Present" in full and "Job: Backend engineer at Acme" in full
    run = agents.Run(
        service.Prepared(RagSettings(), "unused"),
        ChatRequest(message="Describe this project"),
        asyncio.Queue(),
    )
    evidence = result.model_dump(exclude={"source_refs"})
    run.results = [evidence]
    bounded = run.evidence()[0]["records"][0]
    assert len(agents.tokens(bounded["text"])) <= 800
    assert "End: Present" not in bounded["text"]
    assert "Job: Backend engineer at Acme" not in bounded["text"]
    for record in (bounded, run.planner_evidence(evidence)["records"][0]):
        assert record["start_month"] == "2026-01"
        assert record["end_month"] is None and record["ongoing"] is True
        assert record["kind"] == "professional"
        assert record["role"] == "Engineer" and record["company"] == "Acme"
        assert record["linked_job"] == {
            "id": first.id,
            "title": "Backend engineer",
            "company": "Acme",
        }

    jobs = database.execute(
        db, database.DatabaseQuery(entity="jobs", skills=term("Python"))
    )
    run.results = [jobs.model_dump(exclude={"source_refs"})]
    job = run.evidence()[0]["records"][0]
    assert "Matching project evidence:" not in job["text"]
    assert job["role"] == "Backend engineer" and job["company"] == "Acme"
    assert job["start_month"] == "2020-01" and job["ongoing"] is False
    assert job["matching_project_count"] == 3
    assert {item["id"] for item in job["matching_projects"]} == {
        projects[0].id,
        projects[1].id,
        project.id,
    }
    assert all("Python" in item["matched_skills"] for item in job["matching_projects"])


@pytest.fixture
def published(db):
    config = RagSettings(
        embeddings={"dimensions": 3},
        retrieval={"candidate_count": 1, "context_count": 1},
    )

    def create(kind, record_id, texts, vector, revision=1):
        source = Source(
            source_type=kind,
            record_id=record_id,
            revision=revision,
            content_hash="hash",
        )
        db.add(source)
        db.flush()
        job = IngestionJob(
            source_id=source.id,
            source_type=kind,
            record_id=record_id,
            label=f"{kind} {record_id}",
            revision=1,
            trigger="test",
            status="succeeded",
            stage="done",
            settings=config.model_dump(),
            fingerprint="hash",
            created_at=now(),
            available_at=now(),
        )
        db.add(job)
        db.flush()
        source.active_job_id = job.id
        for position, value in enumerate(texts):
            db.add(
                Chunk(
                    job_id=job.id,
                    position=position,
                    text=value,
                    token_count=8,
                    embedding=vector,
                )
            )
        db.commit()
        return source

    return config, create


@requires_database
@pytest.mark.parametrize("mode", ["hybrid", "semantic"])
def test_scoped_retrieval_filters_before_ranking_and_keeps_composite_ids(
    db, published, mode
):
    config, publish = published
    config.retrieval.mode = mode
    publish(
        "projects",
        501,
        ["before allowed", "allowed evidence", "after allowed"],
        [0, 1, 0],
    )
    publish("jobs", 501, ["Python Python Python excluded same ID"], [1, 0, 0])
    publish("projects", 502, ["Python Python Python excluded sibling"], [1, 0, 0])
    result = retrieval.search(db, "Python", [1, 0, 0], config, [("projects", 501)])
    assert len(result) == 1
    assert all(
        part.source_type == "projects" and part.record_id == 501
        for part in result[0].window
    )
    assert "excluded" not in retrieval.context(result, 1)[0]
    assert retrieval.search(db, "Python", [1, 0, 0], config, []) == []


@requires_database
def test_scoped_retrieval_excludes_stale_generations_but_preserves_legacy(
    db, published
):
    config, publish = published
    publish("projects", 501, ["previous generation"], [1, 0, 0], revision=2)
    assert retrieval.search(db, "Python", [1, 0, 0], config)
    assert retrieval.search(db, "Python", [1, 0, 0], config, [("projects", 501)]) == []
    assert retrieval.search(
        db, "Python", [1, 0, 0], config, [("projects", 501)], fresh_only=False
    )


def test_empty_retrieval_scope_never_queries_database():
    assert retrieval.search(None, "Python", [1, 0, 0], RagSettings(), []) == []
