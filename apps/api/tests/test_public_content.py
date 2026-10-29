import os

import pytest
from sqlalchemy.exc import OperationalError

from app.chat import providers
from app.content import public
from app.content.models import Job, Project, Skill

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_ADMIN_DB"),
    reason="Run scripts/check.sh for PostgreSQL tests",
)


@pytest.fixture
def portfolio(db):
    python = Skill(keyword="Python")
    sql = Skill(keyword="SQL_analytics")
    growth = Skill(keyword="Growth 50%")
    rust = Skill(keyword="Rust")
    unused = Skill(keyword="Unused")
    db.add_all([python, sql, growth, rust, unused])
    jobs, projects = [], []
    for index in range(15):
        job = Job(
            title=f"Engineer {index}",
            company="Acme" if index < 2 else f"Studio {index}",
            start_month=f"{2010 + index}-01",
            ongoing=index == 1,
            location="Paris" if index == 0 else "",
            summary="    Code\n\nLong overview.  \nNext line.\n",
            small_summary=f"Compact job {index}",
            responsibilities="Deep narrative" if index == 0 else "Delivery",
            achievements="Saved 50%" if index == 0 else "",
        )
        project = Project(
            name=f"Project {index}",
            role="Lead",
            job=job if index != 14 else None,
            start_month=f"{2010 + index}-02",
            ongoing=index == 1,
            small_summary=f"Compact project {index}",
            summary="## Overview\n\nA full story.",
            description="Deep narrative" if index == 0 else "Delivery",
            contribution="    Code\n\nA contribution.  \nNext line.\n",
            outcomes="Saved 50%" if index == 0 else "",
            website_url="https://example.com/project",
            repository_url="https://github.com/example/project",
            skills=[python, sql, growth]
            if index == 0
            else [python]
            if index == 1
            else [rust]
            if index == 14
            else [],
        )
        db.add_all([job, project])
        jobs.append(job)
        projects.append(project)
    sibling = Project(
        name="Associated newer project",
        job=jobs[0],
        start_month="2025-01",
        small_summary="A related project",
        skills=[python],
    )
    undated_job = Job(title="Undated job", company="No dates")
    undated_project = Project(name="Undated project")
    db.add_all([sibling, undated_job, undated_project])
    db.flush()
    return {
        "jobs": jobs,
        "projects": projects,
        "sibling": sibling,
        "undated_job": undated_job,
        "undated_project": undated_project,
        "python": python,
        "sql": sql,
        "growth": growth,
        "rust": rust,
    }


def test_public_browsing_needs_no_session_or_ai_and_leaves_admin_private(
    client,
    portfolio,
    monkeypatch,
):
    def no_ai(*args, **kwargs):
        raise AssertionError("Public browsing must not invoke a model")

    monkeypatch.setattr(providers, "tool_turn", no_ai)
    monkeypatch.setattr(providers, "stream", no_ai)
    client.headers.pop("origin", None)
    for path in (
        "/public/jobs",
        "/public/projects",
        f"/public/jobs/{portfolio['jobs'][0].id}",
        f"/public/projects/{portfolio['projects'][0].id}",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        for private in ("ingestion", "created_at", "updated_at", "action", "token"):
            assert f'"{private}":' not in response.text
    for entity in ("jobs", "projects", "skills", "documents"):
        assert client.get(f"/admin/{entity}").status_code == 401
    assert client.get("/public/documents").status_code == 404
    assert client.post("/public/jobs", json={}).status_code == 405


def test_catalog_paginates_all_records_and_keeps_unfiltered_facets(client, portfolio):
    initial = client.get("/public/jobs").json()
    assert initial["total"] == initial["matched_total"] == 16
    assert initial["page"] == 1 and initial["page_size"] == 12
    assert len(initial["items"]) == 12
    assert initial["items"][0]["id"] == portfolio["jobs"][-1].id
    assert portfolio["jobs"][0].id not in [row["id"] for row in initial["items"]]
    response = client.get(
        "/public/jobs",
        params={
            "q": " deep NARRATIVE ",
            "company": "Acme",
            "status": "past",
            "skill_id": portfolio["python"].id,
            "page": 99,
        },
    )
    assert response.status_code == 200, response.text
    filtered = response.json()
    assert filtered["total"] == 16 and filtered["matched_total"] == 1
    assert filtered["page"] == 1
    assert filtered["items"][0]["id"] == portfolio["jobs"][0].id
    assert filtered["facets"] == initial["facets"]
    assert filtered["facets"]["jobs"] == []
    assert [skill["keyword"] for skill in filtered["facets"]["skills"]] == [
        "Growth 50%",
        "Python",
        "SQL_analytics",
    ]
    assert "Studio 14" in filtered["facets"]["companies"]
    final = client.get("/public/jobs", params={"page": 999}).json()
    assert final["page"] == 2 and len(final["items"]) == 4
    assert final["items"][-1]["id"] == portfolio["undated_job"].id


def test_project_filters_and_facets_cover_full_catalog(client, portfolio):
    initial = client.get("/public/projects").json()
    assert initial["total"] == 17
    assert initial["items"][0]["id"] == portfolio["sibling"].id
    response = client.get(
        "/public/projects",
        params={
            "q": "deep NARRATIVE",
            "kind": "professional",
            "status": "past",
            "job_id": portfolio["jobs"][0].id,
            "skill_id": portfolio["sql"].id,
        },
    )
    assert response.status_code == 200, response.text
    filtered = response.json()
    assert filtered["matched_total"] == 1 and filtered["total"] == 17
    assert filtered["items"][0]["id"] == portfolio["projects"][0].id
    assert filtered["facets"] == initial["facets"]
    assert filtered["facets"]["companies"] == []
    assert len(filtered["facets"]["jobs"]) == 14
    assert [skill["keyword"] for skill in filtered["facets"]["skills"]] == [
        "Growth 50%",
        "Python",
        "Rust",
        "SQL_analytics",
    ]
    personal = client.get(
        "/public/projects",
        params={
            "kind": "personal",
            "skill_id": portfolio["rust"].id,
        },
    ).json()
    assert personal["matched_total"] == 1
    assert personal["items"][0]["job"] is None
    ongoing = client.get("/public/projects", params={"status": "ongoing"}).json()
    assert [row["id"] for row in ongoing["items"]] == [portfolio["projects"][1].id]
    final = client.get("/public/projects", params={"page_size": 48}).json()
    assert final["items"][-1]["id"] == portfolio["undated_project"].id


@pytest.mark.parametrize("entity", ["jobs", "projects"])
@pytest.mark.parametrize("term", ["%", "_", "PYTHON"])
def test_search_is_literal_case_insensitive_and_matches_skills(
    client,
    portfolio,
    entity,
    term,
):
    data = client.get(f"/public/{entity}", params={"q": term}).json()
    ids = {row["id"] for row in data["items"]}
    expected = {portfolio[entity][0].id}
    if term == "PYTHON":
        expected.add(portfolio[entity][1].id)
        if entity == "projects":
            expected.add(portfolio["sibling"].id)
    assert ids == expected
    assert data["matched_total"] == len(expected)


def test_details_preserve_markdown_and_links_with_compact_related_projects(
    client,
    portfolio,
    db,
):
    job = portfolio["jobs"][0]
    project = portfolio["projects"][0]
    job_row = client.get("/public/jobs", params={"q": "Paris"}).json()["items"][0]
    assert job_row["summary"] == job.small_summary
    assert job_row["project_count"] == 2
    assert len(job_row["skills"]) == 3
    job_detail = client.get(f"/public/jobs/{job.id}").json()
    assert job_detail["summary"] == job.summary
    assert job_detail["responsibilities"] == job.responsibilities
    assert job_detail["achievements"] == job.achievements
    assert [row["id"] for row in job_detail["projects"]] == [
        portfolio["sibling"].id,
        project.id,
    ]
    assert job_detail["projects"][1]["summary"] == project.small_summary
    detail = client.get(f"/public/projects/{project.id}").json()
    assert detail["summary"] == project.summary
    assert detail["contribution"] == project.contribution
    assert detail["description"] == project.description
    assert detail["outcomes"] == project.outcomes
    assert detail["website_url"] == project.website_url
    assert detail["repository_url"] == project.repository_url
    assert detail["job"] == {"id": job.id, "title": job.title, "company": job.company}
    assert {skill["id"] for skill in detail["skills"]} == {
        portfolio[key].id for key in ("python", "sql", "growth")
    }
    project.summary = "An updated overview"
    db.flush()
    assert (
        client.get(f"/public/projects/{project.id}").json()["summary"]
        == project.summary
    )
    project_id = project.id
    db.delete(project)
    db.flush()
    assert client.get(f"/public/projects/{project_id}").status_code == 404


@pytest.mark.parametrize("entity", ["jobs", "projects"])
def test_empty_results_missing_records_and_unknown_filters(client, portfolio, entity):
    for params in ({"q": "not-a-real-match", "page": 100}, {"skill_id": 99999999}):
        data = client.get(f"/public/{entity}", params=params).json()
        assert data["items"] == [] and data["matched_total"] == 0
        assert data["total"] > 0 and data["page"] == 1
    assert client.get(f"/public/{entity}/99999999").status_code == 404
    contradictory = client.get(
        "/public/projects",
        params={
            "kind": "personal",
            "job_id": portfolio["jobs"][0].id,
        },
    ).json()
    assert contradictory["matched_total"] == 0


@pytest.mark.parametrize(
    "path",
    [
        "/public/jobs?page=0",
        "/public/projects?page_size=49",
        "/public/jobs?skill_id=-1",
        "/public/projects?job_id=0",
        "/public/jobs?status=invalid",
        "/public/projects?kind=invalid",
        "/public/projects/0",
        "/public/jobs/-1",
        "/public/jobs/not-a-number",
        "/public/jobs?q=" + "a" * 201,
        "/public/jobs?company=" + "a" * 201,
    ],
)
def test_public_query_validation(client, path):
    response = client.get(path)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_empty_catalogs(client):
    for entity in ("jobs", "projects"):
        response = client.get(f"/public/{entity}")
        assert response.status_code == 200
        assert response.json() == {
            "items": [],
            "total": 0,
            "matched_total": 0,
            "page": 1,
            "page_size": 12,
            "facets": {"companies": [], "skills": [], "jobs": []},
        }


def test_database_failures_have_safe_retryable_responses(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OperationalError("private statement", {}, Exception("private error"))

    monkeypatch.setattr(public, "catalog", unavailable)
    monkeypatch.setattr(public, "detail", unavailable)
    for path in (
        "/public/jobs",
        "/public/projects",
        "/public/jobs/1",
        "/public/projects/1",
    ):
        response = client.get(path)
        assert response.status_code == 503
        assert "private" not in response.text
        assert response.headers["cache-control"] == "no-store"
