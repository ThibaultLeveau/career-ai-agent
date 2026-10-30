import asyncio
import re

import pytest

from app.chat import agents, assessment, database, providers, retrieval
from app.chat.schemas import ChatRequest
from tests.test_agents import call, db_result, prepared, turn


def make_run(intent="career", criteria=0):
    value = agents.Run(
        prepared(), ChatRequest(message="Relevant career experience"), asyncio.Queue()
    )
    value.assessment = assessment.Assessment(
        intent=intent,
        question=value.request.message,
        criteria=[
            {"id": f"c{i}", "requirement": f"Requirement {i}", "origin": "explicit"}
            for i in range(1, criteria + 1)
        ],
        search_queries=["Direct experience", "Transferable experience"]
        if intent == "role_fit"
        else [],
    )
    return value


def statuses(value):
    snapshots = []
    while not value.queue.empty():
        item = value.queue.get_nowait()
        if item is not None and item[0] == "status":
            snapshot = item[1]
            assert isinstance(snapshot["stage"], str)
            assert isinstance(snapshot["message"], str)
            assert len({line["id"] for line in snapshot["activities"]}) == len(
                snapshot["activities"]
            )
            for line in snapshot["activities"]:
                assert line["state"] in {"running", "complete", "error"}
                assert line["agent"] and line["message"]
            snapshots.append(snapshot)
    return snapshots


def lines(snapshot):
    return {line["id"]: line for line in snapshot["activities"]}


@pytest.fixture
def backend(monkeypatch):
    async def embed(*args):
        return [1, 0, 0]

    async def rerank(query, candidates, *args):
        return candidates

    monkeypatch.setattr(agents, "catalog", lambda: ["python"])
    monkeypatch.setattr(agents, "query_database", lambda query: db_result(15))
    monkeypatch.setattr(providers, "embed", embed)
    monkeypatch.setattr(agents, "search_evidence", lambda *args: [])
    monkeypatch.setattr(retrieval, "rerank", rerank)
    monkeypatch.setattr(retrieval, "context", lambda *args: ("Verified evidence", []))


def test_parallel_activity_starts_before_specialists_and_preserves_other_lane(
    monkeypatch, backend
):
    async def run():
        value = make_run(criteria=2)
        value.assessment.criteria[0].requirement = "Python"
        value.assessment.criteria[1].requirement = "backend"
        started = {role: asyncio.Event() for role in ("database", "rag")}
        release = {role: asyncio.Event() for role in started}

        async def specialist(self, role, *args):
            started[role].set()
            await release[role].wait()
            if role == "database":
                return database.DatabaseQuery(skills={"value": "python"})
            return agents.SearchQuery(query="Development responsibilities")

        monkeypatch.setattr(agents.Run, "specialist", specialist)
        db_task = asyncio.create_task(
            value.dispatch(
                call(
                    "database_agent",
                    {"question": "Python projects", "criterion_ids": ["c1", "c2"]},
                    "database",
                )
            )
        )
        rag_task = asyncio.create_task(
            value.dispatch(
                call(
                    "rag_agent",
                    {
                        "question": "Development responsibilities",
                        "criterion_ids": ["c1"],
                        "match_type": "related",
                    },
                    "rag",
                )
            )
        )
        await asyncio.gather(*(event.wait() for event in started.values()))
        history = statuses(value)
        current = lines(history[-1])
        assert set(current) == {"database-combined", "rag-broad"}
        assert all(line["state"] == "running" for line in current.values())
        assert "2 criteria together" in current["database-combined"]["message"]
        assert "(Python, backend)" in current["database-combined"]["message"]
        assert not re.search(r"\bc[12]\b", current["database-combined"]["message"])

        release["database"].set()
        await db_task
        history.extend(statuses(value))
        current = lines(history[-1])
        assert current["database-combined"]["state"] == "complete"
        assert current["rag-broad"]["state"] == "running"

        release["rag"].set()
        await rag_task
        history.extend(statuses(value))
        assert all(line["state"] == "complete" for line in lines(history[-1]).values())
        assert not any(
            re.search(r"\b15\b|retrieved|result rows", str(snapshot), re.IGNORECASE)
            for snapshot in history
        )
        # Later completion events must not mutate an earlier in-flight snapshot.
        assert all(line["state"] == "running" for line in lines(history[1]).values())

    asyncio.run(asyncio.wait_for(run(), timeout=5))


@pytest.mark.parametrize(
    "intent,match_type,lane",
    [
        ("role_fit", "exact", "database-separate"),
        ("career", "related", "database-separate"),
        ("career", "exact", "database-combined"),
    ],
)
def test_database_groups_count_unique_criteria_and_remain_running_until_all_finish(
    monkeypatch, intent, match_type, lane
):
    async def run():
        value = make_run(intent=intent, criteria=5)
        for criterion, requirement in zip(
            value.assessment.criteria,
            ["Python", "backend", "leadership", "delivery", "operations"],
            strict=True,
        ):
            criterion.requirement = requirement
        started = [asyncio.Event() for _ in range(3)]
        release = [asyncio.Event() for _ in started]

        async def database(self, task):
            index = int(task.question)
            started[index].set()
            await release[index].wait()
            return {"total": 1}

        monkeypatch.setattr(agents.Run, "database", database)
        tasks = [
            asyncio.create_task(
                value.dispatch(
                    call(
                        "database_agent",
                        {
                            "question": str(index),
                            "criterion_ids": criterion_ids,
                            "match_type": match_type,
                        },
                        f"database-{index}",
                    )
                )
            )
            for index, criterion_ids in enumerate(
                [["c2", "c1", "c2"], ["c3", "c2"], ["c3", "c1"]]
            )
        ]
        await asyncio.gather(*(event.wait() for event in started))
        current = lines(statuses(value)[-1])
        assert set(current) == {lane}
        grouped_message = (
            "Checking combinations of 3 criteria"
            if lane == "database-combined"
            else "Checking 3 criteria independently"
        )
        assert grouped_message in current[lane]["message"]
        assert "(Python, backend, leadership)" in current[lane]["message"]
        assert current[lane]["message"].count("backend") == 1
        assert not re.search(
            r"\bc[1-5]\b|delivery|operations", current[lane]["message"]
        )
        assert "3 criteria together" not in current[lane]["message"]
        assert current[lane]["state"] == "running"

        release[0].set()
        await tasks[0]
        current = lines(statuses(value)[-1])
        assert current[lane]["state"] == "running"
        assert grouped_message in current[lane]["message"]
        assert "(Python, backend, leadership)" in current[lane]["message"]

        release[1].set()
        await tasks[1]
        current = lines(statuses(value)[-1])
        assert current[lane]["state"] == "running"
        remaining_message = (
            "Checking 2 criteria together"
            if lane == "database-combined"
            else "Checking 2 criteria independently"
        )
        assert remaining_message in current[lane]["message"]
        assert "(Python, leadership)" in current[lane]["message"]
        assert "backend" not in current[lane]["message"]

        release[2].set()
        await tasks[2]
        assert lines(statuses(value)[-1])[lane]["state"] == "complete"

    asyncio.run(asyncio.wait_for(run(), timeout=5))


def test_eight_long_unicode_criteria_fit_public_status_message_limits(monkeypatch):
    async def run():
        value = make_run(criteria=8)
        names = [
            "Python",
            "Backend",
            "Leadership",
            "Delivery",
            "Platform",
            "Architecture",
            "Operations",
            "Collaboration",
        ]
        for criterion, name in zip(value.assessment.criteria, names, strict=True):
            criterion.requirement = f"{name}\n\t" + "🚀" * 80 + "    expérience"
        started = [asyncio.Event() for _ in range(2)]
        release = asyncio.Event()

        async def database(self, task):
            started[int(task.question)].set()
            await release.wait()
            return {"total": 1}

        monkeypatch.setattr(agents.Run, "database", database)
        tasks = [
            asyncio.create_task(
                value.dispatch(
                    call(
                        "database_agent",
                        {"question": str(index), "criterion_ids": criterion_ids},
                        f"database-{index}",
                    )
                )
            )
            for index, criterion_ids in enumerate(
                [["c8", "c6", "c4", "c2"], ["c7", "c5", "c3", "c1", "c2"]]
            )
        ]
        await asyncio.gather(*(event.wait() for event in started))
        history = statuses(value)
        current = lines(history[-1])["database-combined"]
        assert "combinations of 8 criteria" in current["message"]
        assert [current["message"].index(name) for name in names] == sorted(
            current["message"].index(name) for name in names
        )
        assert all(current["message"].count(name) == 1 for name in names)
        assert "🚀" in current["message"]
        for snapshot in history:
            messages = [snapshot["message"]] + [
                line["message"] for line in snapshot["activities"]
            ]
            for message in messages:
                assert len(message.encode("utf-16-le")) // 2 <= 500
                assert "\n" not in message and "\t" not in message
                assert "  " not in message
                assert not re.search(r"\bc[1-8]\b", message)

        release.set()
        await asyncio.gather(*tasks)

    asyncio.run(asyncio.wait_for(run(), timeout=5))


def test_rag_groups_count_searches_and_keep_scoped_searches_separate(monkeypatch):
    async def run():
        value = make_run(criteria=2)
        started = [asyncio.Event() for _ in range(4)]
        release = [asyncio.Event() for _ in started]

        async def rag(self, task):
            index = int(task.question)
            started[index].set()
            await release[index].wait()
            return {"text": "Evidence"}

        monkeypatch.setattr(agents.Run, "rag", rag)
        tasks = [
            asyncio.create_task(
                value.dispatch(
                    call(
                        "rag_agent",
                        {
                            "question": str(index),
                            "criterion_ids": ["c1", "c2"],
                            "result_set": "results-1" if index == 3 else None,
                        },
                        f"rag-{index}",
                    )
                )
            )
            for index in range(4)
        ]
        await asyncio.gather(*(event.wait() for event in started))
        current = lines(statuses(value)[-1])
        assert set(current) == {"rag-broad", "rag-scoped"}
        assert "3 searches across career text" in current["rag-broad"]["message"]
        assert re.search(r"\b1\b", current["rag-scoped"]["message"])
        assert all(line["state"] == "running" for line in current.values())
        for index, wording in [(0, "2 searches"), (1, "1 search")]:
            release[index].set()
            await tasks[index]
            current = lines(statuses(value)[-1])
            assert (
                f"Running {wording} across career text"
                in current["rag-broad"]["message"]
            )
            assert all(line["state"] == "running" for line in current.values())

        release[2].set()
        await tasks[2]
        current = lines(statuses(value)[-1])
        assert current["rag-broad"]["state"] == "complete"
        assert current["rag-scoped"]["state"] == "running"
        release[3].set()
        await tasks[3]
        assert all(
            line["state"] == "complete" for line in lines(statuses(value)[-1]).values()
        )

    asyncio.run(asyncio.wait_for(run(), timeout=5))


@pytest.mark.parametrize("failure", ["provider", "cancellation"])
@pytest.mark.parametrize("role,lane", [("database", "database"), ("rag", "rag-broad")])
def test_failed_or_cancelled_research_never_leaves_a_running_lane(
    monkeypatch, failure, role, lane
):
    async def run():
        value = make_run()
        started = asyncio.Event()
        release = asyncio.Event()

        async def specialist(self, *args):
            started.set()
            await release.wait()
            raise providers.ChatError()

        monkeypatch.setattr(agents.Run, "specialist", specialist)
        task = asyncio.create_task(
            value.dispatch(call(f"{role}_agent", {"question": "Relevant experience"}))
        )
        await started.wait()
        assert lines(statuses(value)[-1])[lane]["state"] == "running"
        if failure == "cancellation":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            release.set()
            assert "error" in await task
        current = lines(statuses(value)[-1])
        assert current[lane]["state"] != "running"
        if failure == "provider":
            assert current[lane]["state"] == "error"

    asyncio.run(asyncio.wait_for(run(), timeout=5))


def test_empty_database_completes_before_fallback_rag_starts(monkeypatch):
    async def run():
        value = make_run()
        fallback_started = asyncio.Event()
        release = asyncio.Event()

        async def database(self, task):
            return {"kind": "database", "total": 0}

        async def rag(self, task):
            fallback_started.set()
            await release.wait()
            return {"kind": "rag", "text": "Related experience"}

        monkeypatch.setattr(agents.Run, "database", database)
        monkeypatch.setattr(agents.Run, "rag", rag)
        task = asyncio.create_task(
            value.dispatch(
                call(
                    "database_agent",
                    {"question": "Missing technology", "fallback_to_rag": True},
                )
            )
        )
        await fallback_started.wait()
        history = statuses(value)
        current = lines(history[-1])
        assert current["database"]["state"] == "complete"
        assert current["rag-broad"]["state"] == "running"
        assert all(
            lines(snapshot)["database"]["state"] == "complete"
            for snapshot in history
            if "rag-broad" in lines(snapshot)
        )
        release.set()
        result = await task
        assert result["total"] == 0 and result["fallback"]["text"]
        assert all(
            line["state"] == "complete" for line in lines(statuses(value)[-1]).values()
        )

    asyncio.run(asyncio.wait_for(run(), timeout=5))


def test_analyzer_and_answer_statuses_follow_actual_phase_transitions(monkeypatch):
    async def run():
        value = make_run()
        observed = []
        decisions = 0

        async def assess(*args):
            observed.append(("understanding", statuses(value)))
            return value.assessment

        async def analyze(self, role, *args, **kwargs):
            nonlocal decisions
            assert role == "query_analyzer"
            observed.append(
                ("planning" if decisions == 0 else "reviewing", statuses(value))
            )
            decisions += 1
            if decisions == 1:
                return turn(call("database_agent", {"question": "Python"}))
            return turn(call("compose_answer", {}))

        async def database(self, task):
            evidence = {"kind": "database", "total": 1, "records": []}
            self.results.append(evidence)
            return evidence

        async def stream(*args, **kwargs):
            observed.append(("combining", statuses(value)))
            yield "Verified answer"

        monkeypatch.setattr(assessment, "assess", assess)
        monkeypatch.setattr(agents, "catalog", lambda: ["python"])
        monkeypatch.setattr(agents.Run, "turn", analyze)
        monkeypatch.setattr(agents.Run, "database", database)
        monkeypatch.setattr(providers, "stream", stream)
        await value.produce()
        assert [phase for phase, _ in observed] == [
            "understanding",
            "planning",
            "reviewing",
            "combining",
        ]
        for phase, history in observed:
            current = history[-1]
            assert current["stage"] == (
                "answering" if phase == "combining" else "analyzing"
            )
            assert len(current["activities"]) == 1
            activity = current["activities"][0]
            assert activity["agent"] == (
                "Answer Agent" if phase == "combining" else "Query Analyzer Agent"
            )
            assert activity["state"] == "running"
            assert phase in activity["message"].lower()

    asyncio.run(asyncio.wait_for(run(), timeout=5))
