import asyncio
import json

import httpx
import pytest

from app.admin.schemas import Generation
from app.chat import providers

TOOLS = [
    {
        "name": "search_career",
        "description": "Search career evidence with explicit constraints.",
        "parameters": {
            "type": "object",
            "properties": {"skills": {"type": "array", "items": {"type": "string"}}},
            "required": ["skills"],
            "additionalProperties": False,
        },
    }
]


def payload(provider):
    if provider == "openai":
        return {
            "status": "completed",
            "output": [
                {
                    "type": "reasoning",
                    "id": "reasoning-1",
                    "summary": [],
                    "encrypted_content": "opaque-encrypted-state",
                },
                *[
                    {
                        "type": "function_call",
                        "call_id": f"call-{index}",
                        "id": f"function-{index}",
                        "name": "search_career",
                        "arguments": json.dumps({"skills": [skill]}),
                    }
                    for index, skill in enumerate(("Python", "PHP"))
                ],
            ],
            "usage": {"input_tokens": 80, "output_tokens": 25},
        }
    return {
        "stop_reason": "tool_use",
        "content": [
            {"type": "thinking", "thinking": "private", "signature": "signature"},
            {"type": "text", "text": "Searching the career evidence."},
            *[
                {
                    "type": "tool_use",
                    "id": f"call-{index}",
                    "name": "search_career",
                    "input": {"skills": [skill]},
                }
                for index, skill in enumerate(("Python", "PHP"))
            ],
        ],
        "usage": {"input_tokens": 80, "output_tokens": 25},
    }


def text_payload(provider):
    if provider == "openai":
        return {
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "OK"}]}
            ],
        }
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "OK"}]}


def transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.parametrize(
    "provider,model,low_effort",
    [
        ("openai", "gpt-6-astra", True),
        ("openai", "gpt-6.1-sol", True),
        ("openai", "gpt-4.1", False),
        ("openai", "gpt-6-unknown", False),
        ("anthropic", "claude-sonnet-4-6", False),
        ("anthropic", "gpt-6-astra", False),
    ],
)
def test_reasoning_effort_is_opt_in_for_generation_and_known_models_only(
    provider, model, low_effort
):
    config = Generation(provider=provider, model=model)
    history = [{"role": "user", "content": "Describe Python experience"}]
    _, _, legacy = providers.request(config, "key", history, "Instructions")
    assert "reasoning" not in legacy
    _, _, generation = providers.request(
        config, "key", history, "Instructions", reasoning_effort="low"
    )
    _, _, native_tools = providers.tool_request(
        config, "key", history, "Instructions", TOOLS
    )
    for body in (generation, native_tools):
        if low_effort:
            assert body["reasoning"] == {"effort": "low"}
        else:
            assert "reasoning" not in body


@pytest.mark.parametrize(
    "provider,model,effort,expected",
    [
        ("openai", "gpt-6-astra", "low", {"effort": "low"}),
        ("openai", "gpt-6-astra", None, None),
        ("openai", "gpt-4.1", "low", None),
        ("openai", "gpt-6-unknown", "low", None),
        ("anthropic", "claude-sonnet-4-6", "low", None),
        ("anthropic", "claude-sonnet-4-6", None, None),
    ],
)
def test_stream_preserves_legacy_requests_and_passes_only_supported_reasoning(
    monkeypatch, provider, model, effort, expected
):
    captured = []
    events = (
        [
            {"type": "response.output_text.delta", "delta": "Grounded answer"},
            {"type": "response.completed"},
        ]
        if provider == "openai"
        else [
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Grounded answer"},
            },
            {"type": "message_stop"},
        ]
    )

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            text="".join(f"data: {json.dumps(event)}\n\n" for event in events),
        )

    transport(monkeypatch, handler)

    async def collect():
        options = {} if effort is None else {"reasoning_effort": effort}
        return [
            value
            async for value in providers.stream(
                Generation(provider=provider, model=model),
                "key",
                [{"role": "user", "content": "Describe Python experience"}],
                "Instructions",
                **options,
            )
        ]

    assert asyncio.run(collect()) == ["Grounded answer"]
    assert captured[0]["stream"] is True
    if expected is None:
        assert "reasoning" not in captured[0]
    else:
        assert captured[0]["reasoning"] == expected


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_native_tools_preserve_provider_state_across_multiple_results(
    monkeypatch, provider
):
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=payload(provider) if len(captured) == 1 else text_payload(provider),
        )

    transport(monkeypatch, handler)
    config = Generation(provider=provider, model="chosen-model", max_output_tokens=4096)
    history = [{"role": "user", "content": "Find Python and PHP experience separately"}]
    turn = asyncio.run(
        providers.tool_turn(
            config,
            "secret",
            history,
            "Use verified data",
            TOOLS,
            tool_choice="required",
        )
    )
    assert [call.arguments for call in turn.calls] == [
        {"skills": ["Python"]},
        {"skills": ["PHP"]},
    ]
    assert turn.usage == {"input_tokens": 80, "output_tokens": 25}
    assert "private" not in turn.text
    updated = providers.append_results(
        history, turn, {"call-0": {"total": 12}, "call-1": {"total": 3}}
    )
    assert len(history) == 1
    next_turn = asyncio.run(
        providers.tool_turn(config, "secret", updated, "Use verified data", TOOLS)
    )
    assert next_turn.text == "OK" and not next_turn.calls
    body = captured[0]
    assert body["model"] == "chosen-model" and body["stream"] is False
    if provider == "openai":
        assert body["store"] is False
        assert body["include"] == ["reasoning.encrypted_content"]
        assert body["tool_choice"] == "required"
        assert body["tools"][0]["strict"] is False
        assert body["tools"][0]["parameters"] == TOOLS[0]["parameters"]
        assert captured[1]["input"] == updated
        assert updated[1:4] == payload(provider)["output"]
        assert [item["call_id"] for item in updated[-2:]] == ["call-0", "call-1"]
        assert json.loads(updated[-2]["output"]) == {"total": 12}
    else:
        assert body["tool_choice"] == {"type": "any"}
        assert body["tools"][0]["input_schema"] == TOOLS[0]["parameters"]
        assert captured[1]["messages"] == updated
        assert updated[-2] == {
            "role": "assistant",
            "content": payload(provider)["content"],
        }
        assert updated[-1]["role"] == "user"
        assert [item["tool_use_id"] for item in updated[-1]["content"]] == [
            "call-0",
            "call-1",
        ]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_required_tool_call_rejects_text_only_response(monkeypatch, provider):
    transport(
        monkeypatch, lambda request: httpx.Response(200, json=text_payload(provider))
    )
    with pytest.raises(providers.ChatError):
        asyncio.run(
            providers.tool_turn(
                Generation(provider=provider, model="test"),
                "key",
                [{"role": "user", "content": "Search"}],
                "Instructions",
                TOOLS,
                tool_choice="required",
            )
        )


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(
    "malformation", ["arguments", "duplicate", "incomplete", "empty"]
)
def test_tool_responses_reject_malformed_or_incomplete_results(provider, malformation):
    result = payload(provider)
    items = result["output" if provider == "openai" else "content"]
    if malformation == "arguments":
        items[-1]["arguments" if provider == "openai" else "input"] = (
            "[]" if provider == "openai" else []
        )
    elif malformation == "duplicate":
        items.append(items[-1])
    elif malformation == "incomplete":
        result["status" if provider == "openai" else "stop_reason"] = (
            "incomplete" if provider == "openai" else "max_tokens"
        )
    else:
        items.clear()
    with pytest.raises(providers.ChatError):
        providers.parse_tool_turn(provider, result)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_append_results_rejects_missing_or_unknown_calls(provider):
    turn = providers.parse_tool_turn(provider, payload(provider))
    for results in ({"call-0": {}}, {"call-0": {}, "call-1": {}, "unknown": {}}):
        with pytest.raises(ValueError):
            providers.append_results([], turn, results)


@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_tool_http_errors_are_sanitized(monkeypatch, status):
    transport(
        monkeypatch, lambda request: httpx.Response(status, text="private-secret")
    )
    with pytest.raises(providers.ChatError) as error:
        asyncio.run(
            providers.tool_turn(
                Generation(model="test"), "private-key", [], "Instructions", TOOLS
            )
        )
    assert "private" not in str(error.value)
