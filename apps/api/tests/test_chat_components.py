import asyncio
import json
from contextlib import contextmanager

import pytest
from pydantic import ValidationError

from app.admin.schemas import ChatComponents, RagSettings
from app.chat import agents, components, presentation, providers, query_engine
from app.chat.query_schema import DatabaseRequest, SelectQuery
from app.chat.schemas import ChatRequest, DetailAction
from app.chat.text import bounded_history
from app.content.models import Project
from tests.test_agent_database import career as career
from tests.test_agent_database import requires_database
from tests.test_agents import call, db_result, prepared, turn
from tests.test_agents import career_assessment as career_assessment


def selection(type, reference, introduction="Here is the work behind that experience."):
    return {"type": type, "reference": reference, "introduction": introduction}


def test_component_defaults_and_invalid_settings():
    assert RagSettings().chat_components == ChatComponents(
        project_list_page_size=5, job_list_page_size=5
    )
    for value in [0, 21, 2.5, True, "5"]:
        with pytest.raises(ValidationError):
            ChatComponents(project_list_page_size=value)


def test_component_tokens_are_typed_and_authenticated():
    token = components.seal(components.DetailScope(entity="projects", id=42))
    assert (
        components.detail_scope(DetailAction(type="show_project", token=token)).id == 42
    )
    with pytest.raises(components.ComponentError):
        components.detail_scope(DetailAction(type="show_job", token=token))
    with pytest.raises(components.ComponentError):
        components.unseal(token, components.ListScope)
    with pytest.raises(components.ComponentError):
        components.unseal(token[:-10] + "tampered!!", components.DetailScope)


def test_list_selections_preserve_verified_membership_and_match_type():
    targets = {
        "exact": components.Target("project_list", [1, 2, 3]),
        "related": components.Target("project_list", [4], "related"),
        "project-1": components.Target("project_card", [1]),
        "job-1-projects": components.Target("project_list", [1], "associated"),
    }
    plan = components.Presentation(
        components=[
            {
                **selection("project_list", "exact"),
                "record_ids": [3, 1],
            }
        ]
    )
    presentation.validate(plan, targets, [])
    assert plan.components[0].record_ids == [3, 1]
    for kind, reference, ids in [
        ("project_list", "exact", [4]),
        ("project_list", "exact", [1, 1]),
        ("project_list", "exact", []),
        ("project_card", "project-1", [1]),
        ("project_list", "job-1-projects", [1]),
    ]:
        with pytest.raises(ValueError):
            presentation.validate(
                components.Presentation(
                    components=[
                        {
                            **selection(kind, reference),
                            "record_ids": ids,
                        }
                    ]
                ),
                targets,
                [],
            )


def test_selections_require_known_references_introductions_and_job_projects():
    targets = {
        "job-1": components.Target("job_card", [1]),
        "job-1-projects": components.Target("project_list", [2]),
    }
    for values in [
        [],
        [selection("job_card", "job-2")],
        [selection("project_card", "job-1")],
        [selection("job_card", "job-1")],
    ]:
        with pytest.raises(ValueError):
            presentation.validate(
                components.Presentation(components=values), targets, ["job-1"]
            )
    with pytest.raises(ValidationError):
        components.Presentation(components=[selection("job_card", "job-1", " ")])
    plan = components.Presentation(
        components=[
            selection("job_card", "job-1"),
            selection("project_list", "job-1-projects"),
        ]
    )
    presentation.validate(plan, targets, ["job-1"])


def test_primary_targets_never_include_supporting_siblings_or_aggregate_lineage():
    targets = {}
    query = DatabaseRequest(
        operation="query",
        query={
            "entity": "projects",
            "select": [{"name": "name", "expression": {"field": "root.name"}}],
        },
    )
    evidence = {
        "primary_refs": [("projects", 1)],
        "page_primary_refs": [("projects", 1)],
    }
    presentation.register(
        targets,
        query,
        evidence,
        [("projects", 1), ("projects", 2), ("jobs", 4)],
        "matches",
        "exact",
    )
    assert targets["matches"].ids == [1]
    assert "project-2" not in targets and "job-4" not in targets
    presentation.register(
        targets,
        query,
        {"primary_refs": [], "page_primary_refs": []},
        [("projects", 1)],
        "aggregate",
        "exact",
    )
    assert "aggregate" not in targets


def test_displayed_references_are_navigation_not_provider_message_fields():
    request = ChatRequest(
        message="Tell me about the second one",
        history=[
            {"role": "user", "content": "Show projects"},
            {
                "role": "assistant",
                "content": "Here are two projects.",
                "components": [
                    {"type": "project", "id": 4, "label": "First"},
                    {"type": "project", "id": 8, "label": "Second"},
                ],
            },
        ],
    )
    history = bounded_history(request)
    assert set(history[-1]) == {"role", "content"}
    assert "navigation only, not evidence" in history[-1]["content"]
    assert "project 8: Second" in history[-1]["content"]


@requires_database
def test_full_scope_pagination_filtering_and_deleted_rows(
    client, db, career, monkeypatch
):
    _, _, projects, _, _, _, unrelated = career
    ids = [p.id for p in reversed(projects)]
    view = components.render(
        db, components.Target("project_list", ids), ChatComponents()
    )
    assert view.total == 7 and len(view.items) == 5
    assert [item.id for item in view.items] == ids[:5]

    def no_model(*args, **kwargs):
        raise AssertionError("List controls must not invoke AI")

    monkeypatch.setattr(providers, "tool_turn", no_model)
    monkeypatch.setattr(providers, "stream", no_model)
    second = client.post("/chat/components/page", json={"token": view.token, "page": 2})
    assert second.status_code == 200
    assert [item["id"] for item in second.json()["items"]] == ids[5:]
    filtered = client.post(
        "/chat/components/page",
        json={"token": view.token, "filter": "Python 0", "page": 2},
    ).json()
    assert filtered["matched_total"] == 1 and filtered["total"] == 7
    assert filtered["page"] == 1 and filtered["items"][0]["id"] == projects[0].id
    no_match = components.page(
        db, components.PageRequest(token=view.token, filter=unrelated.name)
    )
    assert no_match.matched_total == 0 and no_match.items == []
    assert (
        components.page(
            db, components.PageRequest(token=view.token, filter="%")
        ).matched_total
        == 1
    )
    db.delete(projects[0])
    db.flush()
    assert (
        components.page(db, components.PageRequest(token=view.token, page=100)).total
        == 6
    )
    assert second.headers["cache-control"] == "no-store, no-transform"
    invalid = client.post("/chat/components/page", json={"token": "fake"})
    assert invalid.status_code == 400


@requires_database
def test_selected_projects_expand_only_on_show_all_and_prose_uses_selection(
    client,
    db,
    career,
    monkeypatch,
):
    _, _, projects, *_ = career
    ids = [projects[4].id, projects[1].id]

    @contextmanager
    def session(*args):
        yield db

    def no_model(*args, **kwargs):
        raise AssertionError("List controls must not invoke AI")

    monkeypatch.setattr(presentation, "Session", session)
    monkeypatch.setattr(providers, "tool_turn", no_model)
    monkeypatch.setattr(providers, "stream", no_model)
    targets = {"research": components.Target("project_list", [p.id for p in projects])}
    plan = components.Presentation(
        components=[
            {
                **selection("project_list", "research"),
                "record_ids": ids,
            }
        ]
    )
    presentation.validate(plan, targets, [])
    events, _ = presentation.hydrate(
        plan, targets, ChatComponents(project_list_page_size=1)
    )
    view = events[0].component
    assert view.filtered and view.total == 2 and view.unfiltered_total == 11
    assert [item.id for item in view.items] == ids[:1]
    context = presentation.context(events)[0]
    assert context["selected_total"] == 2 and context["records_complete"]
    assert context["selected_records"] == [
        {"id": ids[0], "label": projects[4].name},
        {"id": ids[1], "label": projects[1].name},
    ]
    second = client.post(
        "/chat/components/page", json={"token": view.token, "page": 2}
    ).json()
    assert [item["id"] for item in second["items"]] == ids[1:]
    expanded = client.post(
        "/chat/components/page",
        json={
            "token": view.token,
            "show_all": True,
            "filter": "missing",
            "page": 99,
        },
    ).json()
    assert expanded["total"] == expanded["unfiltered_total"] == 11
    assert (
        not expanded["filtered"] and expanded["filter"] == "" and expanded["page"] == 1
    )
    assert expanded["token"] != view.token
    following = client.post(
        "/chat/components/page",
        json={
            "token": expanded["token"],
            "page": 2,
        },
    ).json()
    assert following["total"] == 11 and following["page"] == 2
    db.delete(projects[4])
    db.flush()
    remaining = components.page(db, components.PageRequest(token=view.token, page=99))
    assert remaining.total == 1 and remaining.page == 1


@requires_database
def test_show_all_stays_in_job_context_and_legacy_tokens_do_not_expand(db, career):
    first, second, projects, ai, php, both, _ = career
    view = components.render(
        db,
        components.Target(
            "project_list",
            [projects[0].id],
            "associated",
            job_id=first.id,
        ),
        ChatComponents(),
    )
    assert view.filtered and view.unfiltered_total == 4
    assert view.scope_label == "Projects from this experience"
    expanded = components.page(
        db, components.PageRequest(token=view.token, show_all=True)
    )
    assert {row.id for row in expanded.items} == {
        projects[0].id,
        projects[1].id,
        ai.id,
        php.id,
    }
    assert both.id not in {row.id for row in expanded.items}
    assert not expanded.filtered and expanded.scope_label == view.scope_label

    legacy = (
        components.cipher()
        .encrypt(
            json.dumps(
                {
                    "purpose": "career_list",
                    "entity": "projects",
                    "ids": [projects[0].id],
                    "page_size": 5,
                }
            ).encode()
        )
        .decode()
    )
    unchanged = components.page(db, components.PageRequest(token=legacy, show_all=True))
    assert [row.id for row in unchanged.items] == [projects[0].id]
    assert unchanged.unfiltered_total is None

    jobs = components.render(
        db, components.Target("job_list", [first.id]), ChatComponents()
    )
    assert jobs.filtered and jobs.unfiltered_total == 2
    all_jobs = components.page(
        db, components.PageRequest(token=jobs.token, show_all=True)
    )
    assert {row.id for row in all_jobs.items} == {first.id, second.id}
    assert not all_jobs.filtered


@requires_database
def test_cards_preserve_markdown_and_lists_use_only_small_summary(db, career):
    job, _, projects, *_ = career
    project = projects[0]
    markdown = "    code\n\nParagraph with a hard break.  \nNext line.\n"
    project.summary = job.summary = markdown
    project.small_summary = "A concise project introduction."
    job.small_summary = "A concise job introduction."
    project.contribution = markdown
    project.website_url = "https://example.com/project"
    project.repository_url = "https://github.com/example/project"
    db.flush()
    assert components.project_row(project).summary == project.small_summary
    assert components.job_row(job).summary == job.small_summary
    detail = components.card(db, "projects", project.id).record
    assert detail.summary == detail.contribution == markdown
    assert detail.website_url == project.website_url
    assert detail.repository_url == project.repository_url
    assert components.card(db, "jobs", job.id).record.summary == markdown
    project.small_summary = ""
    assert components.project_row(project).summary == ""


@requires_database
def test_cards_use_current_fields_and_job_links_ignore_previous_filters(
    db, career, monkeypatch
):
    first, second, projects, ai, php, both, _ = career

    @contextmanager
    def session(*args):
        yield db

    monkeypatch.setattr(presentation, "Session", session)
    targets = {f"job-{first.id}": components.Target("job_card", [first.id])}
    catalog = presentation.catalog(targets)
    linked = next(item for item in catalog if item["type"] == "project_list")
    assert set(targets[linked["reference"]].ids) == {
        projects[0].id,
        projects[1].id,
        ai.id,
        php.id,
    }
    plan = components.Presentation(
        components=[
            selection("job_card", f"job-{first.id}"),
            selection("project_list", linked["reference"]),
        ]
    )
    views, sources = presentation.hydrate(
        plan, targets, ChatComponents(project_list_page_size=2)
    )
    assert views[0].component.record.company == "Acme"
    assert views[1].component.total == 4 and len(views[1].component.items) == 2
    assert sources[0].source_type == "job"
    assert components.associated_projects(db, second.id) == [both.id]
    personal = components.card(db, "projects", projects[-1].id).record
    assert personal.kind == "personal" and personal.job is None and personal.ongoing
    assert personal.skills == ["Python"]
    professional = components.card(db, "projects", projects[0].id).record
    assert (
        professional.job.id == first.id
        and professional.description == "Improved capacity 50%"
    )
    projects[0].description = "Updated description"
    db.flush()
    assert (
        components.card(db, "projects", projects[0].id).record.description
        == "Updated description"
    )
    db.delete(projects[-1])
    db.flush()
    with pytest.raises(components.ComponentError, match="no longer available"):
        components.card(db, "projects", personal.id)


@requires_database
def test_query_primary_membership_preserves_order_without_join_duplicates(db, career):
    result = query_engine.execute(
        db,
        SelectQuery.model_validate(
            {
                "entity": "projects",
                "alias": "p",
                "joins": [{"relationship": "p.skills", "alias": "s"}],
                "select": [{"name": "name", "expression": {"field": "p.name"}}],
                "order_by": [{"column": "name", "direction": "asc"}],
                "limit": 1,
            }
        ),
    )
    ids = [id for _, id in result["primary_refs"]]
    assert len(ids) == len(set(ids))
    names = [db.get(Project, id).name for id in ids]
    assert names == sorted(names)
    assert len(result["page_primary_refs"]) == 1


@requires_database
def test_chat_component_settings_round_trip_preserves_other_sections(client):
    assert (
        client.patch("/admin/settings", json={"chat_components": {}}).status_code == 401
    )
    client.post(
        "/admin/login", json={"username": "owner", "password": "initial-test-password"}
    )
    before = client.get("/admin/settings").json()
    response = client.patch(
        "/admin/settings",
        json={
            "chat_components": {
                "project_list_page_size": 2,
                "job_list_page_size": 8,
            }
        },
    )
    assert response.status_code == 200
    after = response.json()
    assert after.pop("chat_components") == {
        "project_list_page_size": 2,
        "job_list_page_size": 8,
    }
    before.pop("chat_components")
    assert before == after
    assert (
        client.patch(
            "/admin/settings", json={"chat_components": {"job_list_page_size": 0}}
        ).status_code
        == 422
    )


def test_database_runs_before_rag_or_answer_even_if_model_skips_it(monkeypatch):
    replies = [
        turn(call("compose_answer", {})),
        turn(call("rag_agent", {"question": "impact"})),
        turn(call("database_agent", {"question": "Find relevant records"})),
        turn(call("query_database", {})),
        turn(call("compose_answer", {})),
    ]
    seen = []

    async def tool_turn(config, key, messages, instructions, tools, **kwargs):
        seen.append([tool["name"] for tool in tools])
        return replies.pop(0)

    async def stream(*args, **kwargs):
        yield "The database result could be verified."

    monkeypatch.setattr(providers, "tool_turn", tool_turn)
    monkeypatch.setattr(providers, "stream", stream)
    monkeypatch.setattr(agents, "catalog", lambda: [])
    monkeypatch.setattr(agents, "query_database", lambda query: db_result(0))

    async def present(self, messages):
        return []

    monkeypatch.setattr(agents.Run, "present", present)
    output = asyncio.run(_collect(ChatRequest(message="What work had an impact?")))
    assert "event: done" in output
    assert "rag_agent" not in seen[0] and "rag_agent" not in seen[1]
    assert "rag_agent" in seen[-1]


async def _collect(request):
    return "".join([item async for item in agents.answer(prepared(), request)])


def test_presentation_repair_and_component_event_follow_text(monkeypatch):
    token = components.seal(
        components.ListScope(entity="projects", ids=[], page_size=5)
    )
    view = components.ProjectList(
        token=token, total=0, matched_total=0, page=1, page_size=5, filter="", items=[]
    )
    attempts = []

    async def research(self):
        self.database_attempted = True
        self.presentation_targets["verified"] = components.Target("project_list", [])

    async def tool_turn(config, key, messages, instructions, tools, **kwargs):
        attempts.append(messages)
        return turn(
            call(
                "select_presentation",
                {
                    "components": [
                        selection(
                            "project_list",
                            "invented" if len(attempts) == 1 else "verified",
                        )
                    ]
                },
            )
        )

    async def stream(*args, **kwargs):
        yield "There are no exact recorded matches."

    monkeypatch.setattr(agents.Run, "research", research)
    monkeypatch.setattr(providers, "tool_turn", tool_turn)
    monkeypatch.setattr(providers, "stream", stream)
    monkeypatch.setattr(
        presentation,
        "catalog",
        lambda targets: [{"type": "project_list", "reference": "verified", "total": 0}],
    )
    monkeypatch.setattr(
        presentation,
        "hydrate",
        lambda plan, targets, config: (
            [
                components.ComponentEvent(
                    introduction=plan.components[0].introduction, component=view
                )
            ],
            [],
        ),
    )
    output = asyncio.run(_collect(ChatRequest(message="Show matching projects")))
    assert len(attempts) == 2
    assert (
        output.index("event: delta")
        < output.index("event: component")
        < output.index("event: done")
    )
    assert output.count("event: done") == 1 and "invented" not in output
    frame = next(
        frame for frame in output.split("\n\n") if frame.startswith("event: component")
    )
    assert json.loads(frame.split("data: ")[1])["introduction"]


@requires_database
@pytest.mark.parametrize("has_projects", [True, False])
def test_detail_action_reads_current_record_without_research_and_requires_views(
    db, career, monkeypatch, has_projects
):
    from app.content.models import Job

    first = career[0]
    if not has_projects:
        first = Job(title="Independent advisor", company="New company")
        db.add(first)
        db.flush()
    action = components.card(db, "jobs", first.id).record.action

    @contextmanager
    def session(*args):
        yield db

    monkeypatch.setattr(presentation, "Session", session)

    async def unexpected(*args, **kwargs):
        raise AssertionError("Detail identity must not be replanned")

    async def choose(config, key, messages, instructions, tools, **kwargs):
        catalog = json.loads(messages[-1]["content"])["component_catalog"]
        return turn(
            call(
                "select_presentation",
                {
                    "components": [
                        selection(item["type"], item["reference"]) for item in catalog
                    ]
                },
            )
        )

    async def stream(*args, **kwargs):
        yield "Here is the selected experience."

    monkeypatch.setattr(agents.Run, "research", unexpected)
    monkeypatch.setattr(providers, "tool_turn", choose)
    monkeypatch.setattr(providers, "stream", stream)
    output = asyncio.run(_collect(ChatRequest(message="Tell me more", action=action)))
    events = [
        json.loads(frame.split("data: ")[1])
        for frame in output.split("\n\n")
        if frame.startswith("event: component")
    ]
    assert "event: error" not in output and "event: done" in output
    assert [item["component"]["type"] for item in events] == (
        ["job_card", "project_list"] if has_projects else ["job_card"]
    )
    assert events[0]["component"]["record"]["id"] == first.id
    if has_projects:
        assert events[1]["component"]["total"] == 4


def test_associated_projects_cannot_be_presented_as_independent_filtered_matches():
    targets = {
        "job-1": components.Target("job_card", [1]),
        "job-1-projects": components.Target("project_list", [2], "associated"),
    }
    with pytest.raises(ValueError, match="follow their job card"):
        presentation.validate(
            components.Presentation(
                components=[selection("project_list", "job-1-projects")]
            ),
            targets,
            [],
        )
