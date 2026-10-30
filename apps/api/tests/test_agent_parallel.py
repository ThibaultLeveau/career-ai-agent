import asyncio
import json

import pytest

from app.admin.schemas import RagSettings
from app.chat import agents, assessment, database, providers, retrieval, service
from app.chat.schemas import ChatRequest


def call(name, arguments, identifier="call"):
    return providers.ToolCall(identifier, name, arguments)


def turn(*calls):
    return providers.ToolTurn("openai", list(calls), [], "", {})


def make_run(criteria=0):
    config = RagSettings(chat={"model": "test"}, agents={"enabled": True})
    prepared = service.Prepared(config, "key", "key", agent_keys={"openai": "key"})
    value = agents.Run(
        prepared, ChatRequest(message="Relevant career experience"), asyncio.Queue()
    )
    value.assessment = assessment.Assessment(
        intent="role_fit" if criteria else "career",
        question=value.request.message,
        criteria=[
            {
                "id": f"c{i}",
                "label": f"Criterion {i}",
                "requirement": f"Requirement {i}",
                "origin": "explicit",
            }
            for i in range(1, criteria + 1)
        ],
        search_queries=["Direct experience", "Transferable experience"]
        if criteria
        else [],
    )
    return value


def db_result(total=1):
    return database.DatabaseResult(
        entity="projects",
        total=total,
        offset=0,
        limit=5,
        has_more=False,
        records=[
            database.DatabaseRecord(
                id=1,
                type="project",
                label="Verified project",
                text="Verified project experience",
                matched_skills=[],
            )
        ]
        if total
        else [],
        source_refs=[("projects", 1)] if total else [],
        applied_criteria={},
        skill_matches={},
        counts={"projects": total, "jobs": 0},
    )


@pytest.fixture
def backend(monkeypatch):
    async def specialist(self, role, question, *args):
        if role == "database":
            return database.DatabaseQuery(skills={"value": question["question"]})
        return agents.SearchQuery(query=question["question"])

    async def embed(*args):
        return [1, 0, 0]

    async def rerank(query, candidates, *args):
        return candidates

    monkeypatch.setattr(agents, "catalog", lambda: ["python", "PHP"])
    monkeypatch.setattr(agents.Run, "specialist", specialist)
    monkeypatch.setattr(agents, "query_database", lambda query: db_result())
    monkeypatch.setattr(providers, "embed", embed)
    monkeypatch.setattr(agents, "search_evidence", lambda *args: [])
    monkeypatch.setattr(retrieval, "rerank", rerank)
    monkeypatch.setattr(
        retrieval, "context", lambda *args: ("Verified semantic experience", [])
    )


def planner(monkeypatch, calls):
    messages_seen = []

    async def analyze(self, role, messages, tools, *args, **kwargs):
        assert role == "query_analyzer"
        assert {item["name"] for item in tools} == {
            "database_agent",
            "rag_agent",
            "compose_answer",
        }
        messages_seen.append(messages)
        if len(messages_seen) == 1:
            return turn(*calls)
        return turn(call("compose_answer", {}))

    monkeypatch.setattr(agents.Run, "turn", analyze)
    return messages_seen


@pytest.mark.parametrize("intent", ["career", "role_fit"])
def test_initial_database_and_rag_research_run_concurrently(
    monkeypatch, backend, intent
):
    async def run():
        value = make_run(criteria=1 if intent == "role_fit" else 0)
        started = {role: asyncio.Event() for role in ("database", "rag")}
        criterion_ids = ["c1"] if intent == "role_fit" else []

        async def specialist(self, role, question, *args):
            started[role].set()
            await started["rag" if role == "database" else "database"].wait()
            if role == "database":
                return database.DatabaseQuery(skills={"value": "python"})
            return agents.SearchQuery(query="Development responsibilities")

        monkeypatch.setattr(agents.Run, "specialist", specialist)
        messages = planner(
            monkeypatch,
            [
                call(
                    "rag_agent",
                    {
                        "question": "Development responsibilities",
                        "match_type": "exact" if intent == "role_fit" else "related",
                        "criterion_ids": criterion_ids,
                    },
                    "rag",
                ),
                call(
                    "database_agent",
                    {"question": "Python", "criterion_ids": criterion_ids},
                    "database",
                ),
            ],
        )
        await asyncio.wait_for(value.research(), timeout=5)
        assert {item["kind"] for item in value.results} == {"database", "rag"}
        assert len(messages) == 2
        assert not value.limitations

    asyncio.run(run())


def test_independent_database_criteria_execute_concurrently(monkeypatch, backend):
    async def run():
        value = make_run(criteria=3)
        started = {f"c{i}": asyncio.Event() for i in range(1, 4)}

        async def threadpool(function, *args):
            if function is agents.query_database:
                started[args[0].skills.value].set()
                await asyncio.gather(*(event.wait() for event in started.values()))
                return db_result()
            return function(*args)

        monkeypatch.setattr(agents, "run_in_threadpool", threadpool)
        planner(
            monkeypatch,
            [
                call(
                    "database_agent",
                    {"question": criterion, "criterion_ids": [criterion]},
                    criterion,
                )
                for criterion in started
            ],
        )
        await asyncio.wait_for(value.research(), timeout=5)
        assert {tuple(item["criterion_ids"]) for item in value.results} == {
            (criterion,) for criterion in started
        }
        assert len({item["result_set"] for item in value.results}) == 3
        assert not value.limitations

    asyncio.run(run())


def test_database_fallback_starts_before_other_database_finishes(monkeypatch, backend):
    async def run():
        value = make_run(criteria=2)
        slow_started = asyncio.Event()
        slow_finished = asyncio.Event()
        fallback_started = asyncio.Event()
        fallback_tasks = []
        specialist = agents.Run.specialist

        async def record_specialist(self, role, question, *args):
            if role == "rag":
                assert slow_started.is_set() and not slow_finished.is_set()
                assert len(messages) == 1
                fallback_tasks.append(question)
                fallback_started.set()
            return await specialist(self, role, question, *args)

        async def threadpool(function, *args):
            if function is agents.query_database:
                if args[0].skills.value == "Missing technology":
                    await slow_started.wait()
                    return db_result(0)
                slow_started.set()
                await fallback_started.wait()
                slow_finished.set()
                return db_result()
            return function(*args)

        monkeypatch.setattr(agents.Run, "specialist", record_specialist)
        monkeypatch.setattr(agents, "run_in_threadpool", threadpool)
        messages = planner(
            monkeypatch,
            [
                call(
                    "database_agent",
                    {
                        "question": "Missing technology",
                        "criterion_ids": ["c1"],
                        "fallback_to_rag": True,
                    },
                    "empty",
                ),
                call(
                    "database_agent",
                    {"question": "Other criterion", "criterion_ids": ["c2"]},
                    "slow",
                ),
            ],
        )
        await asyncio.wait_for(value.research(), timeout=5)
        assert fallback_tasks[0]["question"] == "Missing technology"
        assert fallback_tasks[0]["criterion_ids"] == ["c1"]
        assert fallback_tasks[0]["match_type"] == "related"
        assert fallback_tasks[0]["result_set"] is None
        exact = next(item for item in value.results if item.get("total") == 0)
        assert exact["match_type"] == "exact" and "fallback" not in exact
        assert len(value.results) == 3 and value.operations == 3
        assert len(messages) == 2

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["provider", "operation_limit"])
def test_failed_fallback_preserves_exact_database_zero(monkeypatch, backend, failure):
    monkeypatch.setattr(agents, "query_database", lambda query: db_result(0))

    async def unavailable(*args):
        raise providers.ChatError()

    monkeypatch.setattr(providers, "embed", unavailable)

    async def run():
        value = make_run()
        if failure == "operation_limit":
            value.operations = value.operation_limit - 1
        result = await value.dispatch(
            call(
                "database_agent",
                {"question": "Missing skill", "fallback_to_rag": True},
            )
        )
        assert result["total"] == 0 and result["match_type"] == "exact"
        assert "error" in result["fallback"]
        assert len(value.results) == 1 and value.results[0]["total"] == 0
        assert "fallback" not in value.results[0]
        assert value.scopes[result["result_set"]] == []
        assert value.limitations
        assert value.operations <= value.operation_limit

    asyncio.run(run())


@pytest.mark.parametrize("total,fallback", [(0, False), (1, True)])
def test_database_fallback_requires_opt_in_and_zero_results(
    monkeypatch, backend, total, fallback
):
    monkeypatch.setattr(agents, "query_database", lambda query: db_result(total))

    async def no_rag(*args):
        pytest.fail("RAG must not run without an opted-in zero result")

    monkeypatch.setattr(agents.Run, "rag", no_rag)

    async def run():
        value = make_run()
        result = await value.dispatch(
            call(
                "database_agent",
                {"question": "Python", "fallback_to_rag": fallback},
            )
        )
        assert result["total"] == total and "fallback" not in result
        assert value.operations == 1

    asyncio.run(run())


def test_all_eight_criteria_support_database_rag_and_specialist_repairs(monkeypatch):
    async def run():
        value = make_run(criteria=8)
        attempts = {}

        async def tool_turn(self, role, messages, *args, **kwargs):
            if role == "query_analyzer":
                return turn(
                    *(
                        call(
                            name,
                            {
                                "question": f"Requirement {i}",
                                "criterion_ids": [f"c{i}"],
                                "match_type": "exact"
                                if name == "database_agent"
                                else "related",
                            },
                            f"{name}-{i}",
                        )
                        for i in range(1, 9)
                        for name in ("database_agent", "rag_agent")
                    )
                )
            task = json.loads(messages[0]["content"])["research"]
            criterion = task["criterion_ids"][0]
            if role == "database":
                attempts[criterion] = attempts.get(criterion, 0) + 1
                return turn(
                    call(
                        "query_database",
                        {"raw_sql": "invalid"}
                        if attempts[criterion] == 1
                        else {"skills": {"value": criterion}},
                    )
                )
            return turn(call("search_evidence", {"query": criterion}))

        async def embed(*args):
            return [1, 0, 0]

        async def rerank(*args):
            return []

        monkeypatch.setattr(agents.Run, "turn", tool_turn)
        monkeypatch.setattr(agents, "catalog", lambda: ["python"])
        monkeypatch.setattr(agents, "query_database", lambda query: db_result())
        monkeypatch.setattr(providers, "embed", embed)
        monkeypatch.setattr(agents, "search_evidence", lambda *args: [])
        monkeypatch.setattr(retrieval, "rerank", rerank)
        monkeypatch.setattr(retrieval, "context", lambda *args: ("Evidence", []))
        await value.research()
        assert value.operation_limit == 24 and value.operations == 24
        assert attempts == {f"c{i}": 2 for i in range(1, 9)}
        assert len(value.results) == 16
        for criterion in attempts:
            assert {
                item["kind"]
                for item in value.results
                if criterion in item["criterion_ids"]
            } == {"database", "rag"}

    asyncio.run(run())


def test_rag_only_research_reaches_representative_as_an_answer(monkeypatch, backend):
    async def run():
        value = make_run()
        seen = []

        async def assess(*args):
            return value.assessment

        async def present(self, messages):
            return []

        async def stream(config, key, messages, *args, **kwargs):
            seen.append(json.loads(messages[-1]["content"]))
            yield "I have demonstrated this work in my projects."

        monkeypatch.setattr(assessment, "assess", assess)
        monkeypatch.setattr(agents.Run, "present", present)
        monkeypatch.setattr(providers, "stream", stream)
        messages = planner(
            monkeypatch,
            [call("rag_agent", {"question": "Describe development responsibilities"})],
        )
        await value.produce()
        assert seen[0]["composition"]["mode"] == "answer"
        assert seen[0]["evidence"][0]["text"] == "Verified semantic experience"
        assert not seen[0]["limitations"] and not value.database_attempted
        events = []
        while not value.queue.empty():
            events.append(value.queue.get_nowait())
        assert (
            "delta",
            {"text": "I have demonstrated this work in my projects."},
        ) in events
        assert ("done", {"sources": []}) in events
        assert len(messages) == 2

    asyncio.run(run())


def test_canceling_research_cancels_every_parallel_specialist(monkeypatch, backend):
    async def run():
        value = make_run()
        started = {role: asyncio.Event() for role in ("database", "rag")}
        canceled = set()
        never = asyncio.Event()

        async def specialist(self, role, *args):
            started[role].set()
            try:
                await never.wait()
            except asyncio.CancelledError:
                canceled.add(role)
                raise

        monkeypatch.setattr(agents.Run, "specialist", specialist)
        planner(
            monkeypatch,
            [
                call("database_agent", {"question": "Python"}, "database"),
                call(
                    "rag_agent",
                    {"question": "Related development", "match_type": "related"},
                    "rag",
                ),
            ],
        )
        research = asyncio.create_task(value.research())
        try:
            await asyncio.wait_for(
                asyncio.gather(*(event.wait() for event in started.values())), timeout=5
            )
        finally:
            research.cancel()
            with pytest.raises(asyncio.CancelledError):
                await research
        assert canceled == {"database", "rag"}

    asyncio.run(run())
