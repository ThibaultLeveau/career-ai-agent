import asyncio
import json
import os

import pytest

from app.admin.models import ProviderKey, RagConfiguration
from app.admin.schemas import RagSettings
from app.admin.security import cipher
from app.chat import agents, database, providers, service
from app.chat.schemas import ChatRequest


@pytest.fixture(autouse=True)
def career_assessment(monkeypatch):
    from app.chat import assessment

    async def assess(config, key, request):
        return assessment.Assessment(intent="career", question=request.message)

    monkeypatch.setattr(assessment, "assess", assess)


def turn(*calls):
    return providers.ToolTurn("openai", list(calls), [], "", {})


def call(name, arguments, id="call"):
    return providers.ToolCall(id, name, arguments)


def prepared():
    config = RagSettings(chat={"model": "test"}, agents={"enabled": True})
    return service.Prepared(config, "key", "key", agent_keys={"openai": "key"})


def db_result(total=7, skill="python"):
    return database.DatabaseResult(
        entity="projects",
        total=total,
        offset=0,
        limit=5,
        has_more=total > 5,
        records=[
            database.DatabaseRecord(
                id=i,
                type="project",
                label=f"Project {i}",
                text=f"Verified {skill} evidence {i}",
                matched_skills=[skill],
            )
            for i in range(1, min(total, 5) + 1)
        ],
        source_refs=[("projects", i) for i in range(1, total + 1)],
        applied_criteria={"skills": {"op": "term", "value": skill}},
        skill_matches={skill: [skill]},
        counts={"projects": total, "jobs": min(total, 2)},
    )


def collect(prep, message="All Python experiences"):
    async def run():
        return [
            item async for item in agents.answer(prep, ChatRequest(message=message))
        ]

    return asyncio.run(run())


def install(monkeypatch, replies):
    monkeypatch.setattr(agents, "catalog", lambda: ["python", "PHP", "Agentic AI"])
    recorded = []

    async def tool_turn(config, key, messages, instructions, tools, **kwargs):
        assert "untrusted data" in instructions
        assert kwargs["tool_choice"] == "required"
        if tools[0]["name"] == "select_presentation":
            return turn(call("select_presentation", {"components": []}))
        recorded.append(messages)
        return replies.pop(0)

    async def stream(config, key, messages, instructions, **kwargs):
        recorded.append(json.loads(messages[-1]["content"]))
        assert "first person" in instructions and "verified" in instructions
        yield "Grounded answer"

    monkeypatch.setattr(providers, "tool_turn", tool_turn)
    monkeypatch.setattr(providers, "stream", stream)
    return recorded


def test_database_result_scopes_every_match_not_just_first_page(monkeypatch):
    recorded = install(
        monkeypatch,
        [
            turn(call("database_agent", {"question": "All python projects"})),
            turn(call("query_database", {"skills": {"value": "python"}})),
            turn(
                call(
                    "rag_agent",
                    {"question": "Describe these", "result_set": "results-1"},
                )
            ),
            turn(call("search_evidence", {"query": "Python delivery"})),
            turn(call("compose_answer", {})),
        ],
    )
    monkeypatch.setattr(agents, "query_database", lambda query: db_result())
    scopes = []

    async def embed(*args):
        return [1, 0, 0]

    def search(query, vector, config, scope):
        scopes.append(scope)
        return []

    monkeypatch.setattr(providers, "embed", embed)
    monkeypatch.setattr(agents, "search_evidence", search)
    output = "".join(collect(prepared()))
    assert scopes == [[("projects", i) for i in range(1, 8)]]
    evidence = recorded[-1]["evidence"]
    assert evidence[0]["total"] == 7 and len(evidence[0]["records"]) == 5
    assert "event: status" in output and output.count("event: done") == 1
    assert "event: error" not in output and "query_database" not in output


def test_zero_exact_matches_remains_separate_from_related(monkeypatch):
    recorded = install(
        monkeypatch,
        [
            turn(call("database_agent", {"question": "AI and PHP"})),
            turn(
                call(
                    "query_database",
                    {
                        "skills": {
                            "op": "and",
                            "children": [{"value": "AI"}, {"value": "PHP"}],
                        }
                    },
                )
            ),
            turn(
                call(
                    "database_agent",
                    {"question": "PHP separately", "match_type": "related"},
                )
            ),
            turn(call("query_database", {"skills": {"value": "PHP"}})),
            turn(call("compose_answer", {})),
        ],
    )
    monkeypatch.setattr(
        agents,
        "query_database",
        lambda query: db_result(0 if query.skills.op == "and" else 3, "PHP"),
    )
    output = "".join(collect(prepared(), "AI and PHP in one project"))
    evidence = recorded[-1]["evidence"]
    assert [(item["total"], item["match_type"]) for item in evidence] == [
        (0, "exact"),
        (3, "related"),
    ]
    assert output.index("No recorded projects") < output.index(
        "Searching related experience"
    )


def test_failed_rag_preserves_verified_database_evidence(monkeypatch):
    recorded = install(
        monkeypatch,
        [
            turn(call("database_agent", {"question": "python"})),
            turn(call("query_database", {"skills": {"value": "python"}})),
            turn(call("rag_agent", {"question": "more", "result_set": "results-1"})),
            turn(call("compose_answer", {})),
        ],
    )
    monkeypatch.setattr(agents, "query_database", lambda query: db_result())
    prep = prepared()
    prep = service.Prepared(prep.config, "key", agent_keys=prep.agent_keys)
    output = "".join(collect(prep))
    assert recorded[-1]["evidence"][0]["total"] == 7
    assert recorded[-1]["limitations"] and "event: done" in output


@pytest.mark.parametrize("second_type", ["exact", "related"])
def test_relabeling_does_not_repeat_the_same_database_query(monkeypatch, second_type):
    queries = []

    async def specialist(*args):
        return database.DatabaseQuery(skills={"value": "python"})

    def query_database(query):
        queries.append(query)
        return db_result()

    monkeypatch.setattr(agents.Run, "specialist", specialist)
    monkeypatch.setattr(agents, "query_database", query_database)

    async def run():
        value = agents.Run(prepared(), ChatRequest(message="Python"), asyncio.Queue())
        first = await value.dispatch(
            call("database_agent", {"question": "Python", "match_type": "exact"})
        )
        repeated = await value.dispatch(
            call(
                "database_agent",
                {"question": "Python again", "match_type": second_type},
            )
        )
        assert first["total"] == 7
        assert "already performed" in repeated["error"]
        assert len(value.results) == 1 and value.results[0]["match_type"] == "exact"
        assert value.operations == 2

    asyncio.run(run())
    assert len(queries) == 1


def test_invalid_specialist_request_repairs_once(monkeypatch):
    recorded = install(
        monkeypatch,
        [
            turn(call("database_agent", {"question": "python"})),
            turn(call("query_database", {"raw_sql": "DROP TABLE project"})),
            turn(call("query_database", {"skills": {"value": "python"}})),
            turn(call("compose_answer", {})),
        ],
    )
    monkeypatch.setattr(agents, "query_database", lambda query: db_result(1))
    output = "".join(collect(prepared()))
    assert recorded[-1]["evidence"][0]["total"] == 1
    assert "DROP TABLE" not in output


def test_empty_scope_does_not_search_globally(monkeypatch):
    async def run():
        value = agents.Run(prepared(), ChatRequest(message="test"), asyncio.Queue())
        value.scopes["empty"] = []
        result = await value.dispatch(
            call("rag_agent", {"question": "anything", "result_set": "empty"})
        )
        assert result["text"] == "" and value.operations == 1
        invalid = await value.dispatch(
            call("rag_agent", {"question": "anything", "result_set": "made-up"})
        )
        assert "error" in invalid

    asyncio.run(run())


def test_exact_database_zero_requires_scope_but_allows_labeled_alternatives(
    monkeypatch,
):
    searches = []

    async def specialist(self, role, *args):
        if role == "database":
            return database.DatabaseQuery(skills={"value": "PHP"})
        return agents.SearchQuery(query="PHP experience separately")

    async def embed(*args):
        return [1, 0, 0]

    def search(query, vector, config, scope):
        searches.append(scope)
        return []

    monkeypatch.setattr(agents.Run, "specialist", specialist)
    monkeypatch.setattr(agents, "query_database", lambda query: db_result(0, "PHP"))
    monkeypatch.setattr(providers, "embed", embed)
    monkeypatch.setattr(agents, "search_evidence", search)

    async def run():
        value = agents.Run(
            prepared(), ChatRequest(message="AI and PHP together"), asyncio.Queue()
        )
        exact = await value.dispatch(call("database_agent", {"question": "AI and PHP"}))
        assert exact["total"] == 0
        rejected = await value.dispatch(call("rag_agent", {"question": "AI and PHP"}))
        assert "error" in rejected and searches == []
        related = await value.dispatch(
            call("rag_agent", {"question": "PHP separately", "match_type": "related"})
        )
        assert related["match_type"] == "related" and searches == [None]
        assert value.results[0]["total"] == 0

    asyncio.run(run())


def test_related_database_handle_cannot_be_upgraded_to_exact_rag(monkeypatch):
    async def specialist(self, role, *args):
        assert role == "database", "Rejected scope must not reach the RAG provider"
        return database.DatabaseQuery(skills={"value": "PHP"})

    monkeypatch.setattr(agents.Run, "specialist", specialist)
    monkeypatch.setattr(agents, "query_database", lambda query: db_result(3, "PHP"))

    async def run():
        value = agents.Run(
            prepared(), ChatRequest(message="AI and PHP together"), asyncio.Queue()
        )
        related = await value.dispatch(
            call(
                "database_agent",
                {"question": "PHP separately", "match_type": "related"},
            )
        )
        rejected = await value.dispatch(
            call(
                "rag_agent",
                {
                    "question": "AI and PHP together",
                    "result_set": related["result_set"],
                },
            )
        )
        assert "error" in rejected
        assert len(value.results) == 1 and value.results[0]["match_type"] == "related"

    asyncio.run(run())


def test_parallel_exact_database_request_blocks_unscoped_rag_even_when_rag_is_first(
    monkeypatch,
):
    monkeypatch.setattr(agents, "catalog", lambda: ["PHP", "Agentic AI"])
    monkeypatch.setattr(agents, "query_database", lambda query: db_result(0, "PHP"))
    analyzer_calls = 0

    async def model(config, key, messages, instructions, tools, **kwargs):
        nonlocal analyzer_calls
        name = tools[0]["name"]
        if name == "database_agent":
            analyzer_calls += 1
            if analyzer_calls == 1:
                return turn(
                    call("rag_agent", {"question": "AI and PHP"}, "rag-first"),
                    call(
                        "database_agent", {"question": "AI and PHP"}, "database-second"
                    ),
                )
            return turn(call("compose_answer", {}))
        assert name == "query_database", "Unscoped RAG must be blocked before model use"
        return turn(call("query_database", {"skills": {"value": "PHP"}}))

    monkeypatch.setattr(providers, "tool_turn", model)

    async def run():
        value = agents.Run(
            prepared(), ChatRequest(message="AI and PHP together"), asyncio.Queue()
        )
        await value.research()
        assert len(value.results) == 1 and value.results[0]["kind"] == "database"
        assert value.results[0]["total"] == 0

    asyncio.run(run())


def test_planner_evidence_bounds_full_payload_and_preserves_exact_counts():
    result = db_result(27).model_dump(exclude={"source_refs"})
    result.update(kind="database", match_type="exact", result_set="results-1")
    result["records"] = [
        {**result["records"][0], "id": i, "text": "Long career evidence. " * 1200}
        for i in range(20)
    ]
    bounded = agents.Run.planner_evidence(result)
    assert len(agents.tokens(json.dumps(bounded))) <= (
        agents.CONTEXT_TOKENS // agents.MAX_OPERATIONS
    )
    for key in ("total", "counts", "offset", "limit", "applied_criteria", "result_set"):
        assert bounded[key] == result[key]
    assert bounded["returned_count"] == len(bounded["records"]) < 20
    assert bounded["complete"] is False and bounded["context_limited"]
    assert bounded["details_truncated"] is True
    assert len(result["records"]) == 20
    assert result["records"][0]["text"] == "Long career evidence. " * 1200


def test_planner_evidence_marks_shortened_details_even_when_all_records_fit():
    result = db_result(1).model_dump(exclude={"source_refs"})
    result["records"][0]["text"] = "Long career evidence. " * 1200
    bounded = agents.Run.planner_evidence(result)
    assert len(bounded["records"]) == 1
    assert bounded["details_truncated"] is True
    assert bounded["returned_count"] == 1


def test_relative_date_requests_receive_current_date_at_each_agent_stage(monkeypatch):
    monkeypatch.setattr(agents, "current_date", lambda: "2026-10-27")
    recorded = install(
        monkeypatch,
        [
            turn(call("database_agent", {"question": "Projects started this year"})),
            turn(call("query_database", {"start_from": "2026-01"})),
            turn(call("compose_answer", {})),
        ],
    )
    monkeypatch.setattr(agents, "query_database", lambda query: db_result(1))
    collect(prepared(), "Which projects started this year?")
    assert json.loads(recorded[0][-1]["content"])["current_date"] == "2026-10-27"
    assert json.loads(recorded[1][-1]["content"])["current_date"] == "2026-10-27"
    assert recorded[-1]["current_date"] == "2026-10-27"


def test_all_dispatches_and_repairs_share_operation_limit(monkeypatch):
    async def run():
        value = agents.Run(prepared(), ChatRequest(message="test"), asyncio.Queue())
        value.scopes["empty"] = []
        for _ in range(agents.MAX_OPERATIONS):
            result = await value.dispatch(
                call("rag_agent", {"question": "anything", "result_set": "empty"})
            )
            assert "error" not in result
        result = await value.dispatch(
            call("rag_agent", {"question": "anything", "result_set": "empty"})
        )
        assert "limit" in result["error"] and value.operations == agents.MAX_OPERATIONS

    asyncio.run(run())


def test_research_timeout_still_composes_limited_answer(monkeypatch):
    recorded = install(monkeypatch, [])
    monkeypatch.setattr(agents, "SEARCH_SECONDS", 0.01)

    async def waiting(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(providers, "tool_turn", waiting)
    output = "".join(collect(prepared()))
    assert "event: done" in output and recorded[-1]["limitations"]


def test_representative_can_use_time_saved_by_fast_research(monkeypatch):
    monkeypatch.setattr(agents, "SEARCH_SECONDS", 0.2)
    monkeypatch.setattr(agents, "ANSWER_SECONDS", 0.01)

    async def research(self):
        self.results.append(db_result(1).model_dump(exclude={"source_refs"}))

    async def stream(config, key, messages, instructions, **kwargs):
        assert kwargs["reasoning_effort"] == "low"
        await asyncio.sleep(0.03)
        yield "An answer that used the spare research time"

    monkeypatch.setattr(agents.Run, "research", research)
    monkeypatch.setattr(providers, "stream", stream)
    output = "".join(collect(prepared()))
    assert "spare research time" in output and "event: done" in output
    assert "event: error" not in output


def test_total_deadline_still_cancels_a_stalled_representative(monkeypatch):
    monkeypatch.setattr(agents, "SEARCH_SECONDS", 0.05)
    monkeypatch.setattr(agents, "ANSWER_SECONDS", 0.01)
    cancelled = []

    async def research(self):
        return

    async def stream(*args, **kwargs):
        try:
            yield "Partial reply"
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(agents.Run, "research", research)
    monkeypatch.setattr(providers, "stream", stream)
    output = "".join(collect(prepared()))
    assert "Partial reply" in output and "event: error" in output
    assert "event: done" not in output and cancelled == [True]


def test_disconnect_cancels_inflight_agent(monkeypatch):
    install(monkeypatch, [])

    async def run():
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def waiting(*args, **kwargs):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        monkeypatch.setattr(providers, "tool_turn", waiting)
        iterator = agents.answer(prepared(), ChatRequest(message="test"))
        assert await anext(iterator) == ": connected\n\n"
        assert "status" in await anext(iterator)
        await asyncio.wait_for(entered.wait(), 2)
        await iterator.aclose()
        assert cancelled.is_set()

    asyncio.run(run())


@pytest.mark.skipif(not os.environ.get("TEST_ADMIN_DB"), reason="Requires PostgreSQL")
def test_agent_prepare_does_not_require_embeddings(db, monkeypatch):
    config = RagSettings(chat={"model": "test"}, agents={"enabled": True})
    db.merge(RagConfiguration(id=1, configuration=config.model_dump()))
    db.merge(
        ProviderKey(provider="openai", encrypted_key=cipher().encrypt(b"key").decode())
    )
    db.commit()
    monkeypatch.setattr(
        service.retrieval,
        "available",
        lambda *args: pytest.fail(
            "Agentic preparation must not require indexed content"
        ),
    )
    result = service.prepare(db)
    assert not result.empty and result.agent_keys["openai"] == "key"


@pytest.mark.skipif(not os.environ.get("TEST_ADMIN_DB"), reason="Requires PostgreSQL")
def test_agent_defaults_require_authentication(client):
    assert client.get("/admin/agents/defaults").status_code == 401
    client.post(
        "/admin/login", json={"username": "owner", "password": "initial-test-password"}
    )
    response = client.get("/admin/agents/defaults")
    assert response.status_code == 200
    assert response.json()["query_analyzer"]["prompt"]
