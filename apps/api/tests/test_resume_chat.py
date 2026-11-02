import asyncio
import json
import os
from contextlib import nullcontext

import pytest
from pydantic import ValidationError

from app.chat import agents, assessment, providers, resource_reader, resumes, service
from app.chat.agent_prompts import VISITOR_WRITING_RULES
from app.chat.components import ComponentEvent, ResumeDownload
from app.chat.schemas import ChatRequest
from app.content.models import Document
from app.ingestion.models import IngestionJob, Source
from app.ingestion.service import now
from tests.test_assessment import prepared


def assessed(**resume):
    if resume.get("role") and resume.get("requirements"):
        resume.setdefault("opportunity", True)
    return assessment.Assessment(
        intent="career", question="Discuss this opportunity", resume=resume
    )


def candidate(id, title="Backend resume"):
    return {
        "id": id,
        "title": title,
        "filename": f"resume-{id}.pdf",
        "matching_notes": "Backend roles in English",
    }


def install_candidates(monkeypatch, response, rows=None):
    rows = rows if rows is not None else [candidate(2), candidate(1)]
    monkeypatch.setattr(resumes, "catalog", lambda: rows)
    monkeypatch.setattr(resumes, "candidate_text", lambda value: value)
    prompts = []

    async def complete(config, key, prompt, instructions):
        prompts.append(json.loads(prompt))
        assert "untrusted data" in instructions
        assert "Never choose the newest file merely as fallback" in instructions
        assert VISITOR_WRITING_RULES in instructions
        assert "only to the visitor-facing clarification question" in instructions
        return json.dumps(response)

    monkeypatch.setattr(providers, "complete", complete)
    return prompts


def choose(context, request=None):
    return asyncio.run(
        resumes.choose(
            context,
            request or ChatRequest(message="A backend role requiring Python"),
            prepared().config.chat,
            "key",
        )
    )


def collect(iterator):
    async def run():
        return [item async for item in iterator]

    return asyncio.run(run())


def test_resume_gate_requires_role_and_explicit_requirement_or_direct_request(
    monkeypatch,
):
    def unexpected():
        pytest.fail("Ineligible requests must not load documents or call a matcher")

    monkeypatch.setattr(resumes, "catalog", unexpected)
    for context in (
        assessed(),
        assessed(role="Backend engineer"),
        assessed(requirements=["Python"]),
        assessed(opportunity=False, role="Backend engineer", requirements=["Python"]),
        assessed(
            opportunity=True, missing_details_question="What role and requirements?"
        ),
    ):
        assert choose(context) == resumes.Outcome()
    assert assessed(role="Backend engineer", requirements=["Python"]).resume.eligible
    assert assessed(requested=True, only=True).resume.eligible
    with pytest.raises(ValidationError):
        assessed(opportunity=True)
    with pytest.raises(ValidationError):
        assessed(only=True)


def test_assessment_receives_multiturn_opportunity_and_extracts_explicit_details(
    monkeypatch,
):
    request = ChatRequest(
        message="Python APIs are the main responsibility.",
        history=[
            {"role": "user", "content": "I am hiring a backend engineer."},
            {"role": "assistant", "content": "Which responsibilities matter?"},
        ],
    )

    async def complete(config, key, prompt, instructions):
        value = json.loads(prompt)
        assert value["history"][0]["content"] == request.history[0].content
        assert "never inferred requirements" in instructions
        return assessed(
            opportunity=True,
            role="Backend engineer",
            requirements=["Develop Python APIs"],
        ).model_dump_json()

    monkeypatch.setattr(providers, "complete", complete)
    result = asyncio.run(assessment.assess(prepared().config.chat, "key", request))
    assert result.resume.eligible and result.resume.requirements == [
        "Develop Python APIs"
    ]


def test_vague_hiring_assessment_needs_no_invented_role_fit_criteria(monkeypatch):
    async def complete(config, key, prompt, instructions):
        assert "need missing_details_question use intent=career" in instructions
        return json.dumps(
            {
                "intent": "career",
                "question": "I have a job opportunity for you.",
                "resume": {
                    "opportunity": True,
                    "missing_details_question": "Which role and responsibilities?",
                },
            }
        )

    monkeypatch.setattr(providers, "complete", complete)
    value = asyncio.run(
        assessment.assess(
            prepared().config.chat,
            "key",
            ChatRequest(message="I have a job opportunity for you."),
        )
    )
    assert not value.resume.eligible and not value.criteria and not value.search_queries
    with pytest.raises(ValidationError, match="Role fit needs criteria"):
        assessment.Assessment.model_validate(
            {**value.model_dump(), "intent": "role_fit", "search_queries": ["a", "b"]}
        )


def test_grounded_selection_receives_language_notes_and_newest_equivalent_order(
    monkeypatch,
):
    prompts = install_candidates(monkeypatch, {"status": "selected", "document_id": 1})
    result = choose(
        assessed(
            role="Backend engineer",
            requirements=["Python"],
            requested_language="French",
        )
    )
    assert result.document_id == 1
    assert [row["id"] for row in prompts[0]["candidates"]] == [2, 1]
    assert prompts[0]["resume_request"]["requested_language"] == "French"
    assert prompts[0]["candidates"][0]["matching_notes"]


@pytest.mark.parametrize(
    "response",
    [
        {"status": "selected", "document_id": 999},
        {"status": "none"},
        {"status": "selected"},
        {"status": "selected", "document_id": 2, "question": "Why?"},
    ],
)
def test_invalid_or_unmatched_selection_never_falls_back_to_newest(
    monkeypatch, response
):
    install_candidates(monkeypatch, response)
    assert (
        choose(assessed(role="Backend", requirements=["Python"])) == resumes.Outcome()
    )


def test_ambiguous_variants_ask_once_then_omit_until_resolved(monkeypatch):
    install_candidates(
        monkeypatch,
        {"status": "clarify", "question": "Would you prefer French or English?"},
    )
    context = assessed(requested=True, only=True)
    result = choose(context)
    assert result.clarification == "Would you prefer French or English?"
    emitted = collect(resumes.events(result, context))
    assert emitted[0] == ("resume_state", {"clarification_asked": True})
    request = ChatRequest(message="Either", resume_clarification_asked=True)
    assert choose(context, request) == resumes.Outcome()
    install_candidates(monkeypatch, {"status": "selected", "document_id": 1})
    assert choose(context, request).document_id == 1


def test_offers_stay_suppressed_after_history_truncation_but_direct_requests_repeat(
    monkeypatch,
):
    prompts = install_candidates(monkeypatch, {"status": "selected", "document_id": 1})
    request = ChatRequest(message="More about the role", offered_resume_ids=[1, 2])
    assert (
        choose(assessed(role="Backend", requirements=["Python"]), request)
        == resumes.Outcome()
    )
    assert not prompts
    assert choose(assessed(requested=True), request).document_id == 1
    with pytest.raises(ValidationError):
        ChatRequest(message="Hello", offered_resume_ids=[0])


def test_single_direct_request_needs_no_pdf_matching(monkeypatch):
    monkeypatch.setattr(resumes, "catalog", lambda: [candidate(1)])

    def unexpected(*args):
        pytest.fail("A direct request for the only resume requires no matcher")

    monkeypatch.setattr(resumes, "candidate_text", unexpected)
    assert choose(assessed(requested=True, only=True)).document_id == 1


def test_matcher_timeout_and_provider_errors_omit_without_failing_answer(monkeypatch):
    install_candidates(monkeypatch, {"status": "none"})

    async def failing(*args):
        raise providers.ChatError()

    monkeypatch.setattr(providers, "complete", failing)
    assert (
        choose(assessed(role="Backend", requirements=["Python"])) == resumes.Outcome()
    )

    async def stalled(*args):
        await asyncio.sleep(10)

    monkeypatch.setattr(providers, "complete", stalled)
    monkeypatch.setattr(resumes, "MATCH_SECONDS", 0.01)
    assert (
        choose(assessed(role="Backend", requirements=["Python"])) == resumes.Outcome()
    )


@pytest.mark.parametrize("agentic", [False, True])
def test_direct_resume_only_bypasses_research_in_both_modes(monkeypatch, agentic):
    async def assess(*args):
        return assessed(requested=True, only=True)

    async def select(*args):
        return resumes.Outcome(1, "Download my resume here.")

    def unexpected(*args, **kwargs):
        pytest.fail("Resume-only requests must not perform career research")

    view = ComponentEvent(
        introduction="Download my resume here.",
        component=ResumeDownload(
            id=1, title="Resume", filename="resume.pdf", size=5, token="signed"
        ),
    )
    monkeypatch.setattr(assessment, "assess", assess)
    monkeypatch.setattr(resumes, "choose", select)
    monkeypatch.setattr(resumes, "hydrate", lambda _: view)
    monkeypatch.setattr(agents.Run, "research", unexpected)
    monkeypatch.setattr(providers, "embed", unexpected)
    monkeypatch.setattr(providers, "stream", unexpected)
    output = "".join(
        collect(
            service.answer(
                prepared(agentic, empty=True), ChatRequest(message="Your CV?")
            )
        )
    )
    assert "resume_download" in output and output.count("event: done") == 1
    assert "event: error" not in output


@pytest.mark.parametrize("agentic", [False, True])
def test_vague_opportunity_appends_explicit_job_details_question(monkeypatch, agentic):
    question = "Which role and responsibilities are you hiring for?"

    async def assess(*args):
        return assessed(opportunity=True, missing_details_question=question)

    async def research(self):
        self.composition = agents.Compose(mode="clarify", guidance="Ask about the job.")

    async def stream(*args, **kwargs):
        yield "I'd be happy to discuss an opportunity."

    monkeypatch.setattr(assessment, "assess", assess)
    monkeypatch.setattr(agents.Run, "research", research)
    monkeypatch.setattr(providers, "stream", stream)
    output = "".join(
        collect(
            service.answer(
                prepared(agentic, empty=True), ChatRequest(message="I have a job.")
            )
        )
    )
    assert output.count(question) == 1
    assert "resume_download" not in output and "event: error" not in output


@pytest.mark.parametrize("agentic", [False, True])
def test_disconnect_cancels_optional_matching(monkeypatch, agentic):
    cancelled = []

    async def assess(*args):
        return assessed(requested=True, only=True)

    async def match(*args):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(assessment, "assess", assess)
    monkeypatch.setattr(resumes, "choose", match)

    async def run():
        async def consume():
            async for _ in service.answer(
                prepared(agentic), ChatRequest(message="CV please")
            ):
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert cancelled == [True]


@pytest.mark.parametrize("agentic", [False, True])
def test_resume_selection_runs_alongside_career_research(monkeypatch, agentic):
    matching_started = asyncio.Event()
    research_started = asyncio.Event()

    async def assess(*args):
        return assessed(role="Backend", requirements=["Python"])

    async def match(*args):
        matching_started.set()
        await research_started.wait()
        return resumes.Outcome()

    async def researched():
        await matching_started.wait()
        research_started.set()

    async def research(self):
        await researched()
        self.results = [{"kind": "database", "records": [], "total": 0}]

    async def embed(*args):
        await researched()
        return [0.1]

    async def stream(*args, **kwargs):
        yield "A verified career answer."

    monkeypatch.setattr(assessment, "assess", assess)
    monkeypatch.setattr(resumes, "choose", match)
    monkeypatch.setattr(agents.Run, "research", research)
    monkeypatch.setattr(providers, "embed", embed)
    monkeypatch.setattr(providers, "stream", stream)
    monkeypatch.setattr(service, "search_candidates", lambda *args: [])
    monkeypatch.setattr(service.retrieval, "context", lambda *args: ("Evidence", []))

    async def run():
        async with asyncio.timeout(1):
            return "".join(
                [
                    item
                    async for item in service.answer(
                        prepared(agentic), ChatRequest(message="Python backend role")
                    )
                ]
            )

    output = asyncio.run(run())
    assert matching_started.is_set() and research_started.is_set()
    assert "A verified career answer." in output and "event: done" in output


def test_revoked_or_failed_resume_hydration_omits_optional_card(monkeypatch):
    monkeypatch.setattr(resumes, "hydrate", lambda _: None)
    outcome = resumes.Outcome(1, "Download my resume.")
    assert collect(resumes.events(outcome, assessed())) == []

    def failed(_):
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(resumes, "hydrate", failed)
    assert collect(resumes.events(outcome, assessed())) == []
    direct = assessed(requested=True, only=True)
    assert collect(resumes.events(outcome, direct)) == [
        ("delta", {"text": direct.resume.unavailable_reply})
    ]


@pytest.mark.parametrize("agentic", [False, True])
def test_slow_optional_hydration_keeps_completed_career_answer_successful(
    monkeypatch, agentic
):
    hydration_cancelled = []

    async def assess(*args):
        return assessed(role="Backend", requirements=["Python"])

    async def match(*args):
        return resumes.Outcome(1, "Download my resume.")

    async def research(self):
        self.results = [{"kind": "database", "records": [], "total": 0}]

    async def embed(*args):
        return [0.1]

    async def stream(*args, **kwargs):
        yield "The career answer is complete."

    async def slow_hydration(function, *args):
        assert function is resumes.hydrate
        try:
            await asyncio.sleep(10)
        finally:
            hydration_cancelled.append(True)

    monkeypatch.setattr(assessment, "assess", assess)
    monkeypatch.setattr(resumes, "choose", match)
    monkeypatch.setattr(resumes, "run_in_threadpool", slow_hydration)
    monkeypatch.setattr(resumes, "HYDRATE_SECONDS", 10 if agentic else 0.02)
    monkeypatch.setattr(agents, "SEARCH_SECONDS", 0.1)
    monkeypatch.setattr(agents, "ANSWER_SECONDS", 0.1)
    monkeypatch.setattr(agents.Run, "research", research)
    monkeypatch.setattr(providers, "embed", embed)
    monkeypatch.setattr(providers, "stream", stream)
    monkeypatch.setattr(service, "search_candidates", lambda *args: [])
    monkeypatch.setattr(service.retrieval, "context", lambda *args: ("Evidence", []))

    async def run():
        async with asyncio.timeout(1):
            return "".join(
                [
                    item
                    async for item in service.answer(
                        prepared(agentic), ChatRequest(message="Python backend role")
                    )
                ]
            )

    output = asyncio.run(run())
    assert hydration_cancelled == [True]
    assert "The career answer is complete." in output
    assert output.count("event: done") == 1
    assert "event: error" not in output and "event: component" not in output


@pytest.mark.skipif(not os.environ.get("TEST_ADMIN_DB"), reason="Requires PostgreSQL")
def test_resume_matching_reuses_current_text_and_extracts_replaced_pdf(db, monkeypatch):
    doc = Document(title="Resume", filename="cv.pdf", size=5, content=b"%PDF-")
    db.add(doc)
    db.flush()
    source = Source(
        source_type="documents", record_id=doc.id, revision=1, content_hash="x"
    )
    db.add(source)
    db.flush()
    job = IngestionJob(
        source_id=source.id,
        source_type="documents",
        record_id=doc.id,
        revision=1,
        label="Resume",
        trigger="save",
        settings={},
        fingerprint="x",
        plain_text="Current Python resume",
        created_at=now(),
        available_at=now(),
    )
    db.add(job)
    db.flush()
    monkeypatch.setattr(resumes, "Session", lambda _: nullcontext(db))
    monkeypatch.setattr(resumes, "get_engine", lambda: None)
    extracted = []

    def extract(content, **kwargs):
        extracted.append(content)
        return [(1, "Updated French Java resume")]

    monkeypatch.setattr(resource_reader, "extract_bounded", extract)
    assert (
        resumes.candidate_text([candidate(doc.id)])[0]["text"]
        == "Current Python resume"
    )
    assert not extracted
    source.revision = 2
    db.flush()
    assert (
        resumes.candidate_text([candidate(doc.id)])[0]["text"]
        == "Updated French Java resume"
    )
    assert extracted == [b"%PDF-"]
