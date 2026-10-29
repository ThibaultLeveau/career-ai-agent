"""Read-only live-model analytics evaluation against independently authored SQL."""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate_agents import (  # noqa: E402
    Case,
    load_saved,
    readonly_transaction,
    run_case,
)
from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import get_engine  # noqa: E402

RANKING = """SELECT s.keyword, count(DISTINCT ps.project_id)
FROM skill s LEFT JOIN project_skill ps ON ps.skill_id = s.id
GROUP BY s.id, s.keyword ORDER BY count(DISTINCT ps.project_id) DESC, s.keyword, s.id"""
COMPANIES = """SELECT j.company, count(DISTINCT p.id), count(DISTINCT j.id)
FROM job j LEFT JOIN project p ON p.job_id = j.id
GROUP BY j.company ORDER BY count(DISTINCT p.id) DESC, j.company"""
PAIRS = """SELECT other.keyword, count(DISTINCT p.id)
FROM project p JOIN project_skill ps ON ps.project_id=p.id
JOIN skill s ON s.id=ps.skill_id
JOIN project_skill ps2 ON ps2.project_id=p.id
JOIN skill other ON other.id=ps2.skill_id
WHERE lower(s.keyword)='python' AND lower(other.keyword)<>'python'
GROUP BY other.id, other.keyword
ORDER BY count(DISTINCT p.id) DESC, other.keyword, other.id"""
TIMELINE = """SELECT count(DISTINCT month), (SELECT count(*) FROM job)
FROM job j CROSS JOIN LATERAL generate_series(
    to_date(j.start_month, 'YYYY-MM'),
    CASE WHEN j.ongoing THEN date_trunc('month', now() AT TIME ZONE 'Europe/Paris')
         ELSE to_date(j.end_month, 'YYYY-MM') END,
    interval '1 month') AS month"""
CASES = [
    (
        "skills-ranking-en",
        "Please list me all your skills ordered by amount of project",
        RANKING,
        ["skills.keyword", "count_distinct(projects.id)"],
    ),
    (
        "skills-ranking-fr",
        "Liste toutes tes compétences classées par nombre de projets "
        "décroissant, puis par nom. Inclue celles sans projet.",
        RANKING,
        ["skills.keyword", "count_distinct(projects.id)"],
    ),
    (
        "company-counts",
        "For each company, show the number of distinct projects and "
        "jobs, ordered by project count descending then company name. "
        "Include all companies.",
        COMPANIES,
        ["jobs.company", "count_distinct(projects.id)", "count_distinct(jobs.id)"],
    ),
    (
        "python-cooccurrence-fr",
        "Quelles autres compétences sont associées à Python dans les "
        "mêmes projets ? Liste-les toutes par nombre de projets "
        "décroissant puis par nom, sans Python lui-même.",
        PAIRS,
        ["skills.keyword", "count_distinct(projects.id)"],
    ),
    (
        "document-reading",
        "List my uploaded documents, then read the first page of the "
        "first document and summarize its contents.",
        None,
        [],
    ),
    (
        "timeline-coverage",
        "How many months of employment are recorded across all my jobs, "
        "merging overlaps? State unknown dates and use the current "
        "month for ongoing jobs.",
        TIMELINE,
        [
            "coverage_months(jobs.start_month,jobs.end_month,jobs.ongoing)",
            "count_distinct(jobs.id)",
        ],
    ),
]


def descriptor(expr, aliases):
    if expr.get("field"):
        alias, _, name = expr["field"].partition(".")
        return f"{aliases.get(alias)}.{name}"
    if expr.get("function"):
        return (
            expr["function"]
            + "("
            + ",".join(descriptor(a, aliases) for a in expr.get("args", []))
            + ")"
        )
    return str(expr.get("value"))


def projected(result, wanted):
    query = result.get("applied_criteria", {})
    if "rows" not in result or not query.get("select"):
        return None
    aliases = {query.get("alias", "root"): query["entity"]}
    targets = {"skills": "skills", "projects": "projects", "job": "jobs"}
    for join in query.get("joins", []):
        aliases[join["alias"]] = targets[join["relationship"].split(".")[1]]
    names = [descriptor(item["expression"], aliases) for item in query["select"]]
    if not all(item in names for item in wanted):
        return None
    indices = [names.index(item) for item in wanted]
    return [[row[i] for i in indices] for row in result["rows"]]


async def main(args):
    engine = get_engine()
    event.listen(engine, "begin", readonly_transaction)
    config, keys = load_saved()
    failed = False
    for case_id, question, oracle_sql, projection in CASES:
        if args.case and case_id not in args.case:
            continue
        with Session(engine) as db:
            expected = (
                [list(row) for row in db.execute(text(oracle_sql))]
                if oracle_sql
                else None
            )
        case = Case(
            id=case_id,
            label=case_id,
            category="analytics",
            question=question,
            review_expectations=["Complete, grounded answer; sources only in footer."],
        )
        for mode in ["agentic", "rag"] if args.mode == "both" else [args.mode]:
            result = await run_case(case, mode, config, keys, [])
            result["expected_rows"] = expected
            observed = [
                projected(item, projection) for item in result["database_results"]
            ]
            result["analytics_passed"] = (
                expected in observed
                if expected is not None and mode == "agentic"
                else None
            )
            result["inline_sources"] = bool(
                re.search(r"\bsources?\s*:", result["answer"], re.I)
            )
            failed |= (
                bool(result["error"])
                or result["analytics_passed"] is False
                or result["inline_sources"]
            )
            print(json.dumps(result, ensure_ascii=False), flush=True)
    engine.dispose()
    return int(failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--mode", choices=["agentic", "rag", "both"], default="both")
    sys.exit(asyncio.run(main(parser.parse_args())))
