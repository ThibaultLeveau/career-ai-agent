import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.chat import agents, query_catalog, query_engine, resource_reader
from app.chat.query_schema import ReadRequest, SelectQuery
from app.content.models import Document, Job, Project, Skill
from app.ingestion.models import IngestionJob, Source
from app.ingestion.service import now
from tests.test_agent_database import requires_database
from tests.test_agents import call, collect, install, prepared, turn
from tests.test_agents import career_assessment as career_assessment


def f(name):
    return {"field": name}


def fn(name, *args):
    return {"function": name, "args": list(args)}


def column(name, expression):
    return {"name": name, "expression": expression}


def pred(op, left, value):
    return {"op": op, "left": f(left), "right": {"value": value}}


def exists(path, alias, where=None):
    result = {"op": "exists", "relationship": path, "alias": alias}
    if where:
        result["where"] = where
    return result


def execute(db, **kwargs):
    return query_engine.execute(db, SelectQuery.model_validate(kwargs))


@pytest.fixture
def resources(db):
    skills = [Skill(keyword=name) for name in ["Python", "Agentic AI", "PHP"]]
    skills += [Skill(keyword=f"Skill {i:02}") for i in range(46)]
    job = Job(title="Engineer", company="Acme", start_month="2020-01")
    db.add_all([*skills, job])
    db.flush()
    projects = [
        Project(
            name="Both",
            job=job,
            skills=skills[:2],
            start_month="2020-01",
            end_month="2020-06",
        ),
        Project(
            name="Python only",
            job=job,
            skills=[skills[0]],
            start_month="2020-04",
            end_month="2020-12",
        ),
        Project(name="PHP only", job=job, skills=[skills[2]]),
        Project(
            name="Personal 100%_literal",
            skills=[skills[0]],
            start_month="2021-01",
            end_month="2021-03",
        ),
    ]
    db.add_all(projects)
    db.flush()
    return skills, job, projects


def ranking(**kwargs):
    return {**deepcopy(query_catalog.catalog()["example"]["query"]), **kwargs}


@requires_database
def test_complete_skill_ranking_zeroes_ties_and_scope_before_pagination(db, resources):
    _, _, projects = resources
    full = execute(db, **ranking())
    assert full["total"] == 49 and full["complete"]
    assert full["rows"][:3] == [["Python", 3], ["Agentic AI", 1], ["PHP", 1]]
    assert full["rows"][3:] == [[f"Skill {i:02}", 0] for i in range(46)]
    assert full["group_refs"][0] == [
        ("projects", p.id) for p in [*projects[:2], projects[3]]
    ]
    assert full["group_refs"][-1] == []
    page = execute(db, **ranking(limit=1, offset=1))
    assert page["rows"] == [["Agentic AI", 1]] and page["has_more"]
    assert page["source_refs"] == full["source_refs"]
    assert page["group_refs"] == [[("projects", projects[0].id)]]


@requires_database
def test_filtered_rankings_having_and_company_counts_distinct_across_joins(
    db, resources
):
    _, job, projects = resources
    query = ranking()
    query["joins"].append({"relationship": "p.job", "alias": "j"})
    query["where"] = pred("eq", "j.company", "Acme")
    query["having"] = pred("gte", "project_count", 2)
    result = execute(db, **query)
    assert result["rows"] == [["Python", 2]]
    assert set(result["source_refs"]) == {
        ("jobs", job.id),
        *(("projects", p.id) for p in projects[:2]),
    }
    result = execute(
        db,
        entity="jobs",
        alias="j",
        joins=[
            {"relationship": "j.projects", "alias": "p"},
            {"relationship": "p.skills", "alias": "s"},
        ],
        select=[
            column("company", f("j.company")),
            column("projects", fn("count_distinct", f("p.id"))),
            column("jobs", fn("count_distinct", f("j.id"))),
            column("links", fn("count")),
        ],
        group_by=[f("j.company")],
    )
    assert result["rows"] == [["Acme", 3, 1, 4]]


@requires_database
def test_cooccurrence_exists_exclusion_and_no_sibling_scope(db, resources):
    skills, job, projects = resources
    skill_where = {
        "op": "and",
        "children": [
            exists("p.skills", "s1", pred("skill_matches", "s1.keyword", "AI")),
            exists("p.skills", "s2", pred("skill_matches", "s2.keyword", "Python")),
        ],
    }
    result = execute(
        db,
        entity="jobs",
        alias="j",
        select=[column("id", f("j.id"))],
        where=exists("j.projects", "p", skill_where),
    )
    assert result["rows"] == [[job.id]]
    assert set(result["source_refs"]) == {
        ("jobs", job.id),
        ("projects", projects[0].id),
    }
    skill_where["children"][1]["where"]["right"]["value"] = "PHP"
    assert (
        execute(
            db,
            entity="jobs",
            alias="j",
            select=[column("id", f("j.id"))],
            where=exists("j.projects", "p", skill_where),
        )["rows"]
        == []
    )
    no_projects = execute(
        db,
        entity="skills",
        alias="s",
        limit=100,
        select=[column("id", f("s.id"))],
        where={"op": "not", "children": [exists("s.projects", "p")]},
    )
    assert no_projects["rows"] == [[s.id] for s in skills[3:]]
    assert no_projects["source_refs"] == []
    pairs = execute(
        db,
        entity="skills",
        alias="s",
        joins=[
            {"relationship": "s.projects", "alias": "p"},
            {"relationship": "p.skills", "alias": "other"},
        ],
        select=[
            column("skill", f("other.keyword")),
            column("count", fn("count_distinct", f("p.id"))),
        ],
        where={
            "op": "and",
            "children": [
                pred("eq", "s.keyword", "Python"),
                pred("ne", "other.keyword", "Python"),
            ],
        },
        group_by=[f("other.id"), f("other.keyword")],
    )
    assert pairs["rows"] == [["Agentic AI", 1]]


@requires_database
def test_literal_contains_and_short_skill_boundaries(db, resources):
    _, _, projects = resources
    for term in ["%", "_", "%_"]:
        result = execute(
            db,
            entity="projects",
            alias="p",
            select=[column("id", f("p.id"))],
            where=pred("contains", "p.name", term),
        )
        assert result["rows"] == [[projects[-1].id]]
    for term in ["' OR 1=1 --", "OpenAI", "%"]:
        result = execute(
            db,
            entity="skills",
            alias="s",
            select=[column("name", f("s.keyword"))],
            where=pred("skill_matches", "s.keyword", term),
        )
        assert result["rows"] == []


@requires_database
def test_timeline_coverage_merges_overlaps_unknowns_and_arithmetic(db, resources):
    args = [f("p.start_month"), f("p.end_month"), f("p.ongoing")]
    result = execute(
        db,
        entity="projects",
        alias="p",
        select=[
            column("coverage", fn("coverage_months", *args)),
            column("sum", fn("sum", fn("duration_months", *args))),
            column("years", fn("divide", fn("coverage_months", *args), {"value": 12})),
            column("avg", fn("avg", fn("duration_months", *args))),
        ],
    )
    assert result["rows"] == [[15, 18, 1.25, 6]]
    assert any("unknown dates" in s for s in result["limitations"])
    assert "approximate" in result["limitations"][0]
    by_year = execute(
        db,
        entity="projects",
        alias="p",
        select=[
            column("year", fn("year", f("p.start_month"))),
            column("count", fn("count")),
        ],
        group_by=[fn("year", f("p.start_month"))],
        order_by=[{"column": "year"}],
    )
    assert by_year["rows"] == [[2020, 2], [2021, 1], [None, 1]]
    resources[2][0].ongoing = True
    resources[2][0].end_month = None
    db.flush()
    result = execute(
        db,
        entity="projects",
        alias="p",
        select=[column("months", fn("duration_months", *args))],
        where=pred("eq", "p.id", resources[2][0].id),
    )
    current = datetime.now(ZoneInfo("Europe/Paris"))
    assert result["rows"] == [[(current.year - 2020) * 12 + current.month]]


@pytest.mark.parametrize(
    "change",
    [
        {"entity": "administrator"},
        {"select": [column("secret", f("s.password"))]},
        {"select": [column("bad", fn("random"))]},
        {"select": [column("bad", fn("sum", f("s.keyword")))]},
        {"select": [column("bad", fn("sum", fn("count")))]},
        {"joins": [{"relationship": "s.settings", "alias": "secret"}]},
        {"group_by": [fn("count")]},
        {"where": pred("eq", "s.id", "not a number")},
        {"order_by": [{"column": "unknown"}]},
        {"limit": 101},
        {"select": [column("bad", f("s.keyword")), column("count", fn("count"))]},
    ],
)
def test_invalid_or_unauthorized_plans_fail_before_execution(change):
    with pytest.raises((ValueError, ValidationError)):
        query_engine.Compiler(
            SelectQuery.model_validate(
                {
                    "entity": "skills",
                    "alias": "s",
                    "select": [column("id", f("s.id"))],
                    **change,
                }
            ),
            [],
        ).statement()


def test_sql_uses_parameters_not_literal_interpolation():
    value = "'; DELETE FROM skill; --"
    query = SelectQuery.model_validate(
        {
            "entity": "skills",
            "alias": "s",
            "select": [column("id", f("s.id"))],
            "where": pred("contains", "s.keyword", value),
        }
    )
    stmt, _ = query_engine.Compiler(query, []).statement()
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert value not in str(compiled) and value in compiled.params.values()


@requires_database
def test_record_reads_keep_complete_relationships_despite_long_text(db, resources):
    skills, job, projects = resources
    projects[0].description = "lengthy narrative " * 3000
    db.flush()
    for entity, record_id in [
        ("projects", projects[0].id),
        ("skills", skills[0].id),
        ("jobs", job.id),
    ]:
        request = ReadRequest(entity=entity, ids=[record_id], max_chars=100)
        result = resource_reader.render(request, resource_reader.snapshot(db, request))
        record = result["records"][0]
        if entity == "projects":
            assert record["skills"] == [
                {"id": s.id, "keyword": s.keyword} for s in skills[:2]
            ]
            assert len(record["text"]) == 100 and not record["text_complete"]
        else:
            assert len(record["projects"]) == 3
            assert record["projects"][0]["skills"] == [
                {"id": s.id, "keyword": s.keyword} for s in skills[:2]
            ]


@requires_database
def test_current_document_text_without_embeddings_and_stale_fallback(db, monkeypatch):
    doc = Document(title="Resume", filename="resume.pdf", size=5, content=b"%PDF-")
    db.add(doc)
    db.flush()
    source = Source(
        source_type="documents", record_id=doc.id, revision=2, content_hash="x"
    )
    db.add(source)
    db.flush()
    ingestion = IngestionJob(
        source_id=source.id,
        source_type="documents",
        record_id=doc.id,
        revision=2,
        label="Resume",
        trigger="manual",
        settings={},
        fingerprint="x",
        plain_text="Current extracted text",
        created_at=now(),
        available_at=now(),
    )
    db.add(ingestion)
    db.flush()
    request = ReadRequest(entity="documents", ids=[doc.id])

    def unexpected(_, **kwargs):
        pytest.fail("Current text should not need PDF extraction or embeddings")

    monkeypatch.setattr(resource_reader, "extract_bounded", unexpected)
    result = resource_reader.render(request, resource_reader.snapshot(db, request))
    assert result["records"][0]["text"] == "Current extracted text"
    source.revision = 3
    db.flush()
    monkeypatch.setattr(
        resource_reader,
        "extract_bounded",
        lambda _, **kwargs: [(1, "Fresh PDF"), (2, "Second page")],
    )
    request = ReadRequest(entity="documents", ids=[doc.id], page_start=2)
    result = resource_reader.render(request, resource_reader.snapshot(db, request))
    assert result["records"][0]["text"] == "Page 2:\nSecond page"
    assert result["citations"][0]["page_start"] == 2

    def unreadable(_, **kwargs):
        raise ValueError("PDF is unreadable")

    monkeypatch.setattr(resource_reader, "extract_bounded", unreadable)
    result = resource_reader.render(request, resource_reader.snapshot(db, request))
    assert not result["complete"] and result["records"][0]["text"] == ""
    assert result["limitations"] == ["PDF is unreadable"]


def test_real_pdf_extraction_worker_reports_unreadable():
    with pytest.raises(ValueError):
        resource_reader.extract_bounded(b"invalid pdf")


def test_ranking_one_operation_without_embeddings_and_all_rows_in_evidence(monkeypatch):
    rows = [[f"Skill {i}", 49 - i] for i in range(49)]
    recorded = install(
        monkeypatch,
        [
            turn(
                call(
                    "database_agent", {"question": "All skills ranked by project count"}
                )
            ),
            turn(call("query_database", query_catalog.catalog()["example"])),
            turn(call("compose_answer", {})),
        ],
    )
    monkeypatch.setattr(
        agents,
        "query_database",
        lambda _: {
            "entity": "skills",
            "total": 49,
            "rows": rows,
            "columns": [],
            "complete": True,
            "source_refs": [("projects", 1)],
            "group_refs": [[("projects", 1)]] * 49,
        },
    )
    prep = replace(prepared(), embedding_key="")
    output = "".join(collect(prep))
    assert "event: done" in output and "event: error" not in output
    assert recorded[-1]["evidence"][0]["rows"] == rows
    assert recorded[-1]["evidence"][0]["complete"]


def test_general_query_validation_repair_and_group_scope(monkeypatch):
    recorded = install(
        monkeypatch,
        [
            turn(call("database_agent", {"question": "Rank skills"})),
            turn(
                call(
                    "query_database",
                    {
                        "operation": "query",
                        "query": {
                            "entity": "skills",
                            "select": [column("secret", f("root.password"))],
                        },
                    },
                )
            ),
            turn(call("query_database", query_catalog.catalog()["example"])),
            turn(call("compose_answer", {})),
        ],
    )
    monkeypatch.setattr(
        agents,
        "query_database",
        lambda _: {
            "entity": "skills",
            "total": 1,
            "rows": [["Python", 1]],
            "columns": [],
            "source_refs": [("projects", 1)],
            "group_refs": [[("projects", 1)]],
            "complete": True,
        },
    )
    assert "event: done" in "".join(collect(prepared()))
    assert recorded[-1]["evidence"][0]["row_scopes"] == ["results-1-group-1"]
    assert "not in the career catalog" in str(recorded)


def test_table_context_limit_is_disclosed():
    result = agents.Run.table_evidence(
        {"rows": [["x" * 1000, i] for i in range(100)], "total": 100, "complete": True},
        1000,
    )
    assert not result["complete"] and result["context_limited"] and result["has_more"]
    assert result["returned_count"] < 100


def test_only_unchanged_default_prompts_upgrade():
    from pathlib import Path

    from app.admin.schemas import RagSettings
    from app.chat.agent_prompts import DEFAULT_AGENT_PROMPTS

    defaults = json.loads(
        (Path(__file__).parent / "fixtures/previous_agent_prompts.json").read_text()
    )
    old_database = defaults["database"][0]
    old_analyzer = defaults["query_analyzer"][0]
    settings = RagSettings(
        agents={
            "database": {"prompt": old_database},
            "query_analyzer": {"prompt": old_analyzer},
        }
    )
    assert settings.agents.database.prompt == DEFAULT_AGENT_PROMPTS["database"]
    assert (
        settings.agents.query_analyzer.prompt == DEFAULT_AGENT_PROMPTS["query_analyzer"]
    )
    custom = old_database + "Use my custom tone."
    settings = RagSettings(agents={"database": {"prompt": custom}})
    assert settings.agents.database.prompt == custom


def test_extraction_timeout_terminates_child(monkeypatch):
    from unittest.mock import Mock

    context = Mock()
    receiver, sender = Mock(), Mock()
    context.Pipe.return_value = receiver, sender
    receiver.poll.return_value = False
    monkeypatch.setattr(
        resource_reader.multiprocessing, "get_context", lambda _: context
    )
    with pytest.raises(ValueError, match="time limit"):
        resource_reader.extract_bounded(b"%PDF", timeout=0.1)
    context.Process.return_value.terminate.assert_called_once()
    receiver.close.assert_called_once()
    sender.close.assert_called_once()


@requires_database
def test_filtered_left_join_keeps_zero_skills_and_scopes_only_contributors(
    db, resources
):
    query = ranking()
    query["joins"][0]["where"] = exists("p.job", "j", pred("eq", "j.company", "Acme"))
    result = execute(db, **query)
    assert result["total"] == 49 and result["complete"]
    assert result["rows"][:3] == [["Python", 2], ["Agentic AI", 1], ["PHP", 1]]
    assert result["rows"][-1] == ["Skill 45", 0]
    assert ("projects", resources[2][-1].id) not in result["source_refs"]
    assert ("skills", resources[0][0].id) in result["row_entities"][0]
