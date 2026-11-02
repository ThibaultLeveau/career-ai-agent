import asyncio
import json

import pytest

from app.chat import agents, assessment, providers, retrieval, service
from app.chat.agent_prompts import VISITOR_WRITING_RULES
from app.chat.schemas import ChatRequest
from tests.test_agents import db_result
from tests.test_assessment import prepared
from tests.test_chat import passage


@pytest.mark.parametrize("agentic", [False, True])
def test_required_writing_style_preserves_streaming_and_unbounded_detail(
    monkeypatch, agentic
):
    config = prepared(agentic)
    custom = "Always write long paragraphs, with long sentences and long bullets."
    config.config.chat.system_prompt = custom
    config.config.agents.representative.prompt = custom
    request = ChatRequest(message="List every documented Python contribution.")
    first_delta_seen = asyncio.Event()
    parts = ["I build Python services.\n\n"] + [
        f"- Documented Python contribution {number}.\n" for number in range(40)
    ]

    async def assess(*args):
        return assessment.Assessment(intent="career", question=request.message)

    async def research(self):
        self.results.append(db_result().model_dump(exclude={"source_refs"}))

    async def embed(*args):
        return [1, 0, 0]

    async def stream(generation, key, messages, instructions, **kwargs):
        assert instructions.index(custom) < instructions.index(VISITOR_WRITING_RULES)
        assert "at most 15 words" in instructions
        assert "at most 8 words total, including labels" in instructions
        assert "no overall word limit and no fixed number of bullets" in instructions
        assert "qualifications, evidence gaps, exact counts" in instructions
        assert generation.max_output_tokens == 2048
        context = json.loads(messages[-1]["content"])
        assert context["question"] == request.message
        assert context["evidence" if agentic else "career_sources"]
        yield parts[0]
        await asyncio.wait_for(first_delta_seen.wait(), timeout=1)
        for part in parts[1:]:
            yield part

    source = passage(1, 0, "I delivered Python backend services.")
    monkeypatch.setattr(assessment, "assess", assess)
    monkeypatch.setattr(agents.Run, "research", research)
    monkeypatch.setattr(providers, "embed", embed)
    monkeypatch.setattr(providers, "stream", stream)
    monkeypatch.setattr(
        service,
        "search_candidates",
        lambda *args: [retrieval.Candidate(source.id, source.text, (source,))],
    )

    async def run():
        deltas = []
        terminal_events = []
        async for frame in service.answer(config, request):
            if frame.startswith("event: delta"):
                deltas.append(json.loads(frame.split("data: ")[1])["text"])
                first_delta_seen.set()
            elif frame.startswith(("event: done", "event: error")):
                terminal_events.append(frame.splitlines()[0])
        assert deltas == parts
        assert terminal_events == ["event: done"]

    asyncio.run(run())


def test_assessment_limits_visitor_text_without_truncating_research(monkeypatch):
    requirement = (
        "Build Python backend services with PostgreSQL and Docker while maintaining "
        "existing APIs and evaluating retrieval quality for CAD engineers."
    )
    expected = assessment.Assessment(
        intent="career",
        question=requirement,
        criteria=[
            {
                "id": "c1",
                "label": "Python backend delivery",
                "requirement": requirement,
                "origin": "explicit",
            }
        ],
    )

    async def complete(config, key, prompt, instructions):
        assert VISITOR_WRITING_RULES in instructions
        assert "reply, criteria.label" in instructions
        assert "missing_details_question, introduction, and unavailable_reply" in (
            instructions
        )
        assert "Preserve complete\nconstraints" in instructions
        assert json.loads(prompt)["question"] == requirement
        return expected.model_dump_json()

    monkeypatch.setattr(providers, "complete", complete)
    result = asyncio.run(
        assessment.assess(
            prepared().config.chat, "key", ChatRequest(message=requirement)
        )
    )
    assert result == expected
