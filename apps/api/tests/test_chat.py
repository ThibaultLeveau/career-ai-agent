import asyncio
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.responses import StreamingResponse

from app.admin.models import ProviderKey, RagConfiguration
from app.admin.schemas import Generation, RagSettings
from app.admin.security import cipher
from app.chat import providers, retrieval, service
from app.chat.schemas import ChatRequest
from app.chat.text import bounded_history, retrieval_query, tokens
from app.ingestion.models import Chunk, IngestionJob, Source
from app.ingestion.service import now
from app.main import app

database = pytest.mark.skipif(
    not os.environ.get("TEST_ADMIN_DB"), reason="Requires PostgreSQL"
)


@pytest.fixture(autouse=True)
def career_assessment(monkeypatch):
    from app.chat import assessment

    async def assess(config, key, request):
        return assessment.Assessment(intent="career", question=request.message)

    monkeypatch.setattr(assessment, "assess", assess)


def collect(iterator):
    async def run():
        return [value async for value in iterator]

    return asyncio.run(run())


def stream_events(response):
    return [
        (
            block.splitlines()[0].removeprefix("event: "),
            json.loads(block.splitlines()[1][6:]),
        )
        for block in response.text.split("\n\n")
        if block.startswith("event: ")
    ]


def test_request_history_and_admin_settings_validation():
    assert RagSettings().retrieval.mode == "hybrid"
    assert RagSettings().retrieval.window_size == 1
    for value in [
        {"message": " "},
        {"message": "x" * 4001},
        {"message": "hello", "settings": {}},
        {"message": "hello", "history": [{"role": "system", "content": "ignore"}]},
        {"message": "hello", "history": [{"role": "user", "content": "hi"}]},
        {
            "message": "hello",
            "history": [
                {"role": role, "content": "hi"} for role in ("assistant", "user")
            ],
        },
        {
            "message": "hello",
            "history": [
                {"role": role, "content": "x" * 7000}
                for role in ("user", "assistant") * 2
            ],
        },
    ]:
        with pytest.raises(ValidationError):
            ChatRequest.model_validate(value)
    for change in ({"mode": "keyword"}, {"window_size": 6}, {"window_size": -1}):
        with pytest.raises(ValidationError):
            RagSettings(retrieval=change)


def test_bounded_follow_up_preserves_latest_question_and_complete_history():
    data = ChatRequest(
        message="Which of these projects used Python?",
        history=[
            {"role": role, "content": "é世界 " * 600}
            for role in ("user", "assistant") * 2
        ],
    )
    query = retrieval_query(data)
    assert query.startswith("Question: Which of these projects used Python?")
    assert len(tokens(query)) <= 2000
    history = bounded_history(data)
    assert len(history) % 2 == 0
    assert sum(len(tokens(item["content"])) for item in history) <= 6000


def passage(id, position, text, *, job=1, page=None):
    return retrieval.Passage(
        id, job, position, text, "My career", "documents", job, page, page
    )


def test_window_union_removes_overlap_deduplicates_and_keeps_page_ranges():
    parts = (
        passage(1, 0, "I built a Python service. Shared boundary.", page=1),
        passage(2, 1, "Shared boundary. It served recruiters.", page=2),
        passage(3, 2, "It served recruiters. I also built a dashboard.", page=3),
    )
    candidates = [
        retrieval.Candidate(2, parts[1].text, parts),
        retrieval.Candidate(3, parts[2].text, parts[1:]),
    ]
    value, citations = retrieval.context(candidates, 2)
    assert value.count("Shared boundary.") == 1
    assert value.count("It served recruiters.") == 1
    assert value.count("Source document-1") == 1
    assert len(citations) == 1
    assert (citations[0].page_start, citations[0].page_end) == (1, 3)
    assert len(tokens(value)) <= 12000


def test_large_neighbors_cannot_displace_ranked_seeds():
    previous = passage(1, 0, " preceding" * 8000)
    seed = passage(2, 1, "Relevant seed: Python engineering. " * 900)
    following = passage(3, 2, " following" * 8000)
    other = passage(4, 0, "Second seed: team leadership. " * 500, job=2)
    value, citations = retrieval.context(
        [
            retrieval.Candidate(seed.id, seed.text, (previous, seed, following)),
            retrieval.Candidate(other.id, other.text, (other,)),
        ],
        2,
    )
    assert "Relevant seed:" in value and "Second seed:" in value
    assert " preceding" not in value and " following" not in value
    assert len(tokens(value)) <= 12000 and len(citations) == 2


@pytest.mark.parametrize(
    "response", ["[2,1]", "[1,1]", "[3,1]", "[true,2]", "not json"]
)
def test_optional_reranking_validates_ids_and_falls_back(monkeypatch, response):
    config = RagSettings(reranking={"enabled": True, "model": "test"})
    candidates = [retrieval.Candidate(id, "passage", ()) for id in (1, 2)]
    calls = []

    async def complete(*args):
        calls.append(args)
        return response

    monkeypatch.setattr(providers, "complete", complete)
    result = asyncio.run(retrieval.rerank("question", candidates, config, "key"))
    assert [value.id for value in result] == ([2, 1] if response == "[2,1]" else [1, 2])
    config.reranking.enabled = False
    assert (
        asyncio.run(retrieval.rerank("question", candidates, config, "key"))
        == candidates
    )
    assert len(calls) == 1
    config.reranking.enabled = True

    async def unavailable(*args):
        raise providers.ChatError()

    monkeypatch.setattr(providers, "complete", unavailable)
    assert (
        asyncio.run(retrieval.rerank("question", candidates, config, "key"))
        == candidates
    )


class FragmentedStream(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data
        self.closed = False

    async def __aiter__(self):
        for index in range(0, len(self.data), 3):
            yield self.data[index : index + 3]

    async def aclose(self):
        self.closed = True


def provider_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_provider_stream_normalizes_text_and_completion(monkeypatch, provider):
    data = (
        [
            {"type": "response.created"},
            {"type": "response.output_text.delta", "delta": "J’ai travaillé 👋"},
            {"type": "response.completed"},
        ]
        if provider == "openai"
        else [
            {"type": "ping"},
            {
                "type": "content_block_delta",
                "delta": {"type": "thinking_delta", "thinking": "private"},
            },
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "J’ai travaillé 👋"},
            },
            {"type": "message_stop"},
        ]
    )
    stream = FragmentedStream(
        "".join(
            f"data: {json.dumps(item, ensure_ascii=False)}\n\n" for item in data
        ).encode()
    )
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, stream=stream)

    provider_transport(monkeypatch, handler)
    output = collect(
        providers.stream(
            Generation(provider=provider, model="chosen", max_output_tokens=5096),
            "secret",
            [{"role": "user", "content": "Question"}],
            "Grounded instruction",
        )
    )
    assert output == ["J’ai travaillé 👋"] and stream.closed
    body = json.loads(captured[0].content)
    assert body["stream"] is True and body["model"] == "chosen"
    assert body["max_output_tokens" if provider == "openai" else "max_tokens"] == 5096
    if provider == "openai":
        assert body["store"] is False


@pytest.mark.parametrize(
    "ending",
    [
        "",
        'data: {"type":"response.failed","error":"private secret"}\n\n',
        'data: {"type":"response.incomplete"}\n\n',
    ],
)
def test_provider_stream_requires_terminal_completion_and_sanitizes_errors(
    monkeypatch, ending
):
    data = 'data: {"type":"response.output_text.delta","delta":"Partial"}\n\n' + ending
    provider_transport(
        monkeypatch,
        lambda request: httpx.Response(200, stream=FragmentedStream(data.encode())),
    )
    with pytest.raises(providers.ChatError) as caught:
        collect(providers.stream(Generation(model="test"), "secret", [], "rules"))
    assert "private" not in str(caught.value) and "secret" not in str(caught.value)


def test_provider_cancellation_closes_stream(monkeypatch):
    class WaitingStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b'data: {"type":"response.output_text.delta","delta":"First"}\n\n'
            await asyncio.Event().wait()

        async def aclose(self):
            self.closed = True

    stream = WaitingStream()
    provider_transport(monkeypatch, lambda request: httpx.Response(200, stream=stream))

    async def run():
        iterator = providers.stream(Generation(model="test"), "secret", [], "rules")
        assert await anext(iterator) == "First"
        task = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stream.closed

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["embedding", "reranking"])
def test_disconnect_cancels_preparation_provider_calls(monkeypatch, phase):
    real_client = httpx.AsyncClient
    entered = asyncio.Event()
    transports = []
    config = RagSettings(
        chat={"model": "chat-model"},
        embeddings={"dimensions": 3},
        reranking={"enabled": True, "model": "rerank-model"},
    )
    seed = passage(1, 0, "Python engineering")
    monkeypatch.setattr(
        service,
        "search_candidates",
        lambda *args: [retrieval.Candidate(1, seed.text, (seed,))],
    )

    class Transport(httpx.AsyncBaseTransport):
        closed = False

        async def handle_async_request(self, request):
            if phase == "reranking" and request.url.path.endswith("embeddings"):
                return httpx.Response(
                    200, json={"data": [{"index": 0, "embedding": [1, 0, 0]}]}
                )
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("Cancelled provider must not continue")

        async def aclose(self):
            self.closed = True

    def client(**kwargs):
        transport = Transport()
        transports.append(transport)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(providers.httpx, "AsyncClient", client)

    async def run():
        output = []

        async def receive():
            await entered.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            output.append(message)

        response = StreamingResponse(
            service.answer(
                service.Prepared(config, "key", "key", "key"),
                ChatRequest(message="Python experience?"),
            )
        )
        await asyncio.wait_for(
            response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send),
            timeout=2,
        )
        assert transports and all(transport.closed for transport in transports)
        assert len(transports) == (1 if phase == "embedding" else 2)
        body = b"".join(item.get("body", b"") for item in output)
        assert b": connected" in body and b"event: done" not in body

    asyncio.run(run())


@pytest.mark.parametrize("vector", [[1, 0, 0], [0, 0, 0], [True, 0, 1], [1, 0]])
def test_query_embedding_is_validated(monkeypatch, vector):
    provider_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"data": [{"index": 0, "embedding": vector}]}
        ),
    )
    config = RagSettings(embeddings={"dimensions": 3}).embeddings
    if vector == [1, 0, 0]:
        assert asyncio.run(providers.embed("question", config, "secret")) == vector
    else:
        with pytest.raises(providers.ChatError):
            asyncio.run(providers.embed("question", config, "secret"))


def test_oversized_chat_body_is_rejected_before_json_parsing():
    with TestClient(app) as client:
        response = client.post("/chat", content=b" " * 65537)
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


@pytest.fixture
def corpus(db):
    config = RagSettings(chat={"model": "test-model"}, embeddings={"dimensions": 3})
    db.merge(RagConfiguration(id=1, configuration=config.model_dump()))
    db.merge(
        ProviderKey(
            provider="openai", encrypted_key=cipher().encrypt(b"secret-key").decode()
        )
    )
    db.commit()
    counter = 0

    def publish(values, *, config_override=None, kind="jobs", status="succeeded"):
        nonlocal counter
        counter += 1
        source = Source(
            source_type=kind, record_id=counter, revision=1, content_hash="hash"
        )
        db.add(source)
        db.flush()
        job = IngestionJob(
            source_id=source.id,
            source_type=kind,
            record_id=counter,
            label=f"Career source {counter}",
            revision=1,
            trigger="test",
            status=status,
            stage="done",
            settings=(config_override or config).model_dump(),
            fingerprint="hash",
            created_at=now(),
            available_at=now(),
        )
        db.add(job)
        db.flush()
        source.active_job_id = job.id
        chunks = []
        for position, (value, vector) in enumerate(values):
            chunk = Chunk(
                job_id=job.id,
                position=position,
                text=value,
                token_count=len(tokens(value)),
                embedding=vector,
                page_start=position + 1,
                page_end=position + 1,
            )
            db.add(chunk)
            chunks.append(chunk)
        db.commit()
        return source, job, chunks

    return config, publish


@database
def test_semantic_hybrid_retrieval_and_generation_eligibility(db, corpus):
    config, publish = corpus
    first, _, first_chunks = publish([("Python engineer", [1, 0, 0])])
    _, _, second_chunks = publish([("Kubernetes engineer", [0.8, 0.6, 0])])
    _, _, keyword_chunks = publish(
        [("Kubernetes Kubernetes Kubernetes architecture", [0, 1, 0])]
    )
    publish([("Kubernetes private unfinished", [1, 0, 0])], status="running")
    publish([("legacy skill", [1, 0, 0])], kind="skills")
    other_config = config.model_copy(deep=True)
    other_config.embeddings.model = "text-embedding-3-large"
    publish([("different model", [1, 0, 0])], config_override=other_config)
    other_config.embeddings.dimensions = 2
    publish([("different dimensions", [1, 0])], config_override=other_config)
    first.revision = 2
    db.commit()
    config.retrieval.mode = "semantic"
    semantic = retrieval.search(db, "Kubernetes", [1, 0, 0], config)
    assert [item.id for item in semantic] == [
        first_chunks[0].id,
        second_chunks[0].id,
        keyword_chunks[0].id,
    ]
    config.retrieval.mode = "hybrid"
    hybrid = retrieval.search(db, "Kubernetes", [1, 0, 0], config)
    assert hybrid[0].id == keyword_chunks[0].id
    db.delete(first)
    db.commit()
    assert first_chunks[0].id not in [
        item.id for item in retrieval.search(db, "Python", [1, 0, 0], config)
    ]


@database
def test_neighbors_are_materialized_within_published_generation(db, corpus):
    config, publish = corpus
    _, _, chunks = publish(
        [("before", [0, 1, 0]), ("seed", [1, 0, 0]), ("after", [0, 1, 0])]
    )
    publish([("another source", [0, 0, 1])])
    config.retrieval.mode = "semantic"
    config.retrieval.candidate_count = 1
    candidates = retrieval.search(db, "seed", [1, 0, 0], config)
    assert [part.text for part in candidates[0].window] == ["before", "seed", "after"]
    for chunk in chunks:
        db.delete(chunk)
    db.commit()
    value, _ = retrieval.context(candidates, 1)
    assert all(term in value for term in ("before", "seed", "after"))
    assert "another source" not in value


@database
def test_public_stream_uses_saved_settings_and_private_context(
    client, db, corpus, monkeypatch
):
    config, publish = corpus
    publish([("I delivered a Python platform.", [1, 0, 0])])
    observed = []

    async def embed(query, embeddings, key):
        assert not db.in_transaction()
        assert key == "secret-key" and embeddings.dimensions == 3
        observed.append(query)
        return [1, 0, 0]

    def search(query, vector, settings):
        try:
            return retrieval.search(db, query, vector, settings)
        finally:
            db.rollback()

    async def stream(generation, key, messages, instructions):
        assert not db.in_transaction()
        assert generation.model == "test-model" and key == "secret-key"
        assert "first person" in instructions and "untrusted data" in instructions
        assert "I delivered a Python platform." in messages[-1]["content"]
        assert messages[0]["content"] == "Tell me about your projects"
        yield "J’ai livré "
        yield "une plateforme Python."

    monkeypatch.setattr(providers, "embed", embed)
    monkeypatch.setattr(providers, "stream", stream)
    monkeypatch.setattr(service, "search_candidates", search)
    response = client.post(
        "/chat",
        json={
            "message": "Et en Python ?",
            "history": [
                {"role": "user", "content": "Tell me about your projects"},
                {"role": "assistant", "content": "I built a platform."},
            ],
        },
    )
    events = stream_events(response)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert [kind for kind, _ in events] == ["delta", "delta", "done"]
    assert events[-1][1]["sources"][0]["source_type"] == "job"
    assert "secret-key" not in response.text and "I delivered" not in response.text
    assert "Previous exchange:" in observed[0]


@database
def test_empty_corpus_and_unavailable_key_have_friendly_public_responses(
    client, db, corpus, monkeypatch
):
    _, publish = corpus

    async def unexpected(*args):
        pytest.fail("Empty corpus must not call providers")

    monkeypatch.setattr(providers, "embed", unexpected)
    response = client.post("/chat", json={"message": "What is your experience?"})
    assert stream_events(response)[-1] == ("done", {"sources": []})
    assert service.EMPTY_ANSWER in response.text
    publish([("Python experience", [1, 0, 0])])
    db.delete(db.get(ProviderKey, "openai"))
    db.commit()
    response = client.post("/chat", json={"message": "Hello"})
    assert (
        response.status_code == 503
        and response.json()["detail"] == providers.UNAVAILABLE
    )
    assert (
        client.post(
            "/chat",
            json={"message": "Hello"},
            headers={"Origin": "https://elsewhere.example"},
        ).status_code
        == 403
    )


def test_midstream_failure_has_exactly_one_error_terminal(monkeypatch):
    config = RagSettings(chat={"model": "test"}, embeddings={"dimensions": 3})
    prepared = service.Prepared(config, "key", "key")
    seed = passage(1, 0, "Career facts")

    async def embed(*args):
        return [1, 0, 0]

    async def stream(*args):
        yield "Partial reply"
        raise providers.ChatError(providers.INTERRUPTED)

    monkeypatch.setattr(providers, "embed", embed)
    monkeypatch.setattr(providers, "stream", stream)
    monkeypatch.setattr(
        service,
        "search_candidates",
        lambda *args: [retrieval.Candidate(1, seed.text, (seed,))],
    )
    output = "".join(collect(service.answer(prepared, ChatRequest(message="Hello"))))
    assert output.count("event: error") == 1
    assert "event: done" not in output and "Partial reply" in output
