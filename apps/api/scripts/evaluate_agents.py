"""Compare saved-model agentic and RAG answers without changing saved state."""

import argparse
import asyncio
import json
import logging
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import event
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.admin.schemas import RagSettings, agent_generation  # noqa: E402
from app.chat import agents, database, providers, retrieval, service  # noqa: E402
from app.chat.schemas import ChatRequest, HistoryMessage  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.ingestion.service import settings  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests/fixtures/agent_evaluation.json"
RUN_SECONDS = 150
ROLES = ("query_analyzer", "database", "rag", "representative")


class Oracle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: database.DatabaseQuery
    match_type: Literal["exact", "related"] = "exact"
    required: bool = True


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    category: str
    question: str
    history: list[HistoryMessage] = Field(default_factory=list)
    oracles: list[Oracle] = Field(default_factory=list)
    review_expectations: list[str]

    def request(self):
        return ChatRequest(message=self.question, history=self.history)


def readonly_transaction(connection):
    connection.exec_driver_sql("SET TRANSACTION READ ONLY")


def load_saved():
    with Session(get_engine()) as db:
        config = settings(db)
        keys = {
            provider: service.saved_key(db, provider, optional=True)
            for provider in ("openai", "anthropic")
        }
    return config, keys


def prepare(config: RagSettings, keys: dict[str, str], mode: str):
    config = config.model_copy(deep=True)
    config.agents.enabled = mode == "agentic"
    empty = False
    if mode == "agentic":
        for role in ("query_analyzer", "representative"):
            generation = agent_generation(config, role)
            if not generation.model or not keys[generation.provider]:
                raise providers.ChatError()
        key = keys[agent_generation(config, "representative").provider]
    else:
        with Session(get_engine()) as db:
            empty = not retrieval.available(db, config)
        key = keys[config.chat.provider]
        if not empty and (
            not config.chat.model or not key or not keys[config.embeddings.provider]
        ):
            raise providers.ChatError()
    return service.Prepared(
        config=config,
        key=key,
        embedding_key=keys[config.embeddings.provider],
        reranking_key=keys[config.reranking.provider]
        if config.reranking.enabled
        else "",
        empty=empty,
        agent_keys=keys,
    )


def database_metadata(result: dict, refs):
    if result.get("operation", "records") != "records" or "rows" in result:
        return {**result, "source_refs": refs}
    return {
        key: result[key]
        for key in (
            "entity",
            "total",
            "offset",
            "limit",
            "has_more",
            "applied_criteria",
            "skill_matches",
            "counts",
        )
    } | {
        "records": [
            {key: record[key] for key in ("id", "type", "label", "matched_skills")}
            for record in result["records"]
        ],
        "source_refs": refs,
    }


def oracle_results(case: Case):
    with Session(get_engine()) as db:
        return [
            {
                "id": oracle.id,
                "required": oracle.required,
                "match_type": oracle.match_type,
                "query": oracle.query.model_dump(exclude_none=True),
                **database_metadata(
                    (result := database.execute(db, oracle.query)).model_dump(),
                    result.source_refs,
                ),
            }
            for oracle in case.oracles
        ]


def primary_ids(result):
    return {
        record_id
        for kind, record_id in result["source_refs"]
        if kind == result["entity"]
    }


def check_oracles(oracles, observed, mode):
    checks = []
    for oracle in oracles:
        candidates = []
        for result in observed:
            if (
                result.get("operation", "records") != "records"
                or result["entity"] != oracle["entity"]
                or result["match_type"] != oracle["match_type"]
            ):
                continue
            counts_match = (
                result["total"] == oracle["total"]
                and result["counts"] == oracle["counts"]
            )
            membership_matches = primary_ids(result) == primary_ids(oracle)
            page_matches = (
                result["offset"] == oracle["offset"]
                and result["limit"] == oracle["limit"]
                and [record["id"] for record in result["records"]]
                == [record["id"] for record in oracle["records"]]
            )
            candidates.append(
                {
                    "result_set": result["result_set"],
                    "counts_match": counts_match,
                    "membership_matches": membership_matches,
                    "page_matches": page_matches,
                    "criteria_identical": (
                        result["applied_criteria"] == oracle["applied_criteria"]
                    ),
                    "passed": counts_match and membership_matches and page_matches,
                }
            )
        checks.append(
            {
                "oracle_id": oracle["id"],
                "required": oracle["required"],
                "status": "checked" if mode == "agentic" else "not_comparable",
                "passed": any(item["passed"] for item in candidates)
                if mode == "agentic"
                else None,
                "candidates": candidates,
            }
        )
    return checks


async def run_case(case, mode, config, keys, oracles):
    started = perf_counter()
    result = {
        "case_id": case.id,
        "label": case.label,
        "category": case.category,
        "mode": mode,
        "started_at": datetime.now(UTC).isoformat(),
        "question": case.question,
        "history": [item.model_dump() for item in case.history],
        "answer": "",
        "components": [],
        "statuses": [],
        "sources": [],
        "terminal": None,
        "error": None,
        "database_results": [],
        "rag_results": [],
        "limitations": [],
        "model_usage": [],
        "model_usage_note": (
            "Usage covers agent tool decisions only. It excludes the final streamed "
            "Representative answer, embeddings, reranking and RAG baseline streaming."
        ),
        "oracles": oracles,
        "review_expectations": case.review_expectations,
        "review_note": (
            "Checks compare database counts, full membership and displayed pages. "
            "Inspect filters for semantic correctness, especially empty results. "
            "Answer accuracy, language, grounding and presentation require review. "
            "RAG-only has no exact database evidence to compare."
        ),
    }
    run = None

    def consume(name, payload):
        if name == "delta":
            result["answer"] += payload["text"]
        elif name == "component":
            view = dict(payload["component"])
            view.pop("token", None)
            if "items" in view:
                view["items"] = [
                    {k: v for k, v in row.items() if k != "action"}
                    for row in view["items"]
                ]
            if "record" in view:
                view["record"] = {
                    k: v for k, v in view["record"].items() if k != "action"
                }
            result["components"].append(
                {"introduction": payload["introduction"], "component": view}
            )
        elif name == "status":
            result["statuses"].append(
                {
                    "elapsed_seconds": round(perf_counter() - started, 3),
                    "stage": payload["stage"],
                    "message": payload["message"],
                }
            )
        elif name in ("done", "error"):
            if result["terminal"] is not None:
                raise ValueError("Multiple terminal events")
            result["terminal"] = name
            if name == "done":
                result["sources"] = payload.get("sources", [])
            else:
                result["error"] = {
                    "type": "stream_error",
                    "message": payload["message"],
                }

    try:
        prepared = prepare(config, keys, mode)
        result["models"] = (
            {role: agent_generation(config, role).model_dump() for role in ROLES}
            if mode == "agentic"
            else {
                "chat": config.chat.model_dump(exclude={"system_prompt"}),
            }
        )
        async with asyncio.timeout(RUN_SECONDS):
            if mode == "agentic":
                queue = asyncio.Queue()
                run = agents.Run(prepared, case.request(), queue)
                task = asyncio.create_task(run.produce())
                try:
                    while (item := await queue.get()) is not None:
                        consume(*item)
                    await task
                finally:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            else:
                async for chunk in service.answer(prepared, case.request()):
                    for frame in chunk.split("\n\n"):
                        lines = frame.splitlines()
                        names = [
                            line[6:].strip()
                            for line in lines
                            if line.startswith("event:")
                        ]
                        data = [
                            line[5:].strip()
                            for line in lines
                            if line.startswith("data:")
                        ]
                        if names and data:
                            consume(names[0], json.loads("\n".join(data)))
        if result["terminal"] is None:
            result["error"] = {
                "type": "incomplete_stream",
                "message": "No terminal event received.",
            }
    except Exception as error:
        result["error"] = {
            "type": type(error).__name__,
            "message": "Evaluation could not complete; check model and service health.",
        }
    if run is not None:
        result["operations"] = run.operations
        result["limitations"] = list(dict.fromkeys(run.limitations))
        result["model_usage"] = run.model_usage
        for evidence in run.results:
            if evidence["kind"] == "database":
                result["database_results"].append(
                    {
                        **database_metadata(
                            evidence, run.scopes[evidence["result_set"]]
                        ),
                        "match_type": evidence["match_type"],
                        "result_set": evidence["result_set"],
                    }
                )
            elif evidence["kind"] == "rag":
                result["rag_results"].append(
                    {
                        "match_type": evidence["match_type"],
                        "result_set": evidence["result_set"],
                        "evidence_found": bool(evidence["text"]),
                        "limitation": evidence.get("limitation", ""),
                    }
                )
    result["latency_seconds"] = round(perf_counter() - started, 3)
    result["oracle_checks"] = check_oracles(
        oracles,
        result["database_results"],
        mode,
    )
    required = [check for check in result["oracle_checks"] if check["required"]]
    result["structured_checks_passed"] = (
        all(check["passed"] for check in required)
        if mode == "agentic" and required
        else None
    )
    return result


async def evaluate(cases, mode):
    engine = None
    failed = False
    try:
        engine = get_engine()
        event.listen(engine, "begin", readonly_transaction)
        config, keys = load_saved()
        for case in cases:
            oracles = oracle_results(case)
            for selected in ("agentic", "rag") if mode == "both" else (mode,):
                result = await run_case(case, selected, config, keys, oracles)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                failed |= bool(result["error"]) or (
                    result["structured_checks_passed"] is False
                )
    except Exception as error:
        print(
            json.dumps(
                {
                    "error": {
                        "type": type(error).__name__,
                        "message": "Could not read evaluation settings or database.",
                    },
                }
            ),
            flush=True,
        )
        failed = True
    finally:
        if engine is not None:
            engine.dispose()
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("agentic", "rag", "both"), default="both")
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="ID[,ID]",
        help="Select case IDs; repeat the option or separate IDs with commas.",
    )
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument(
        "--list", action="store_true", help="List cases without API calls."
    )
    args = parser.parse_args()
    try:
        cases = [
            Case.model_validate(item) for item in json.loads(args.fixtures.read_text())
        ]
        for case in cases:
            case.request()
    except OSError, ValueError:
        parser.error("Could not read valid evaluation fixtures.")
    ids = {case.id for case in cases}
    if len(ids) != len(cases):
        parser.error("Fixture case IDs must be unique.")
    selected = {value for item in args.case for value in item.split(",") if value}
    if selected - ids:
        parser.error("Unknown case IDs: " + ", ".join(sorted(selected - ids)))
    cases = [case for case in cases if not selected or case.id in selected]
    if args.list:
        for case in cases:
            print(
                json.dumps(
                    {"case_id": case.id, "label": case.label}, ensure_ascii=False
                )
            )
        return 0
    logging.basicConfig(level=logging.ERROR)
    return asyncio.run(evaluate(cases, args.mode))


if __name__ == "__main__":
    sys.exit(main())
