import json
import logging
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.admin.schemas import Embeddings, Generation, Provider

logger = logging.getLogger(__name__)
LOW_EFFORT_MODELS = {
    "gpt-6.1-sol",
    "gpt-6.1-terra",
    "gpt-6-astra",
    "gpt-6-sol",
    "gpt-6-luna",
}

UNAVAILABLE = (
    "The career assistant is temporarily unavailable. Please try again shortly."
)
INTERRUPTED = "The reply was interrupted. Please try again."


class ChatError(Exception):
    def __init__(self, message: str = UNAVAILABLE, status: int = 503):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolTurn:
    provider: Provider
    calls: list[ToolCall]
    continuation: list[dict]
    text: str
    usage: dict


def request(
    config: Generation,
    key: str,
    messages: list[dict],
    instructions: str,
    *,
    streaming: bool = False,
    reasoning_effort: Literal["low"] | None = None,
) -> tuple[str, dict, dict]:
    if not config.model or not key:
        raise ChatError()
    if config.provider == "openai":
        return (
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {key}"},
            {
                "model": config.model,
                "input": messages,
                "instructions": instructions,
                "max_output_tokens": config.max_output_tokens,
                "store": False,
                "stream": streaming,
                **(
                    {"reasoning": {"effort": reasoning_effort}}
                    if reasoning_effort and config.model in LOW_EFFORT_MODELS
                    else {}
                ),
            },
        )
    return (
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
        {
            "model": config.model,
            "messages": messages,
            "system": instructions,
            "max_tokens": config.max_output_tokens,
            "stream": streaming,
        },
    )


def tool_request(
    config: Generation,
    key: str,
    messages: list[dict],
    instructions: str,
    tools: list[dict],
    *,
    tool_choice: Literal["auto", "required"] = "auto",
) -> tuple[str, dict, dict]:
    url, headers, body = request(config, key, messages, instructions)
    if config.provider == "openai":
        body["tools"] = [
            {
                "type": "function",
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
                "strict": False,
            }
            for tool in tools
        ]
        body["tool_choice"] = tool_choice
        body["include"] = ["reasoning.encrypted_content"]
        if config.model in LOW_EFFORT_MODELS:
            body["reasoning"] = {"effort": "low"}
    else:
        body["tools"] = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["parameters"],
            }
            for tool in tools
        ]
        body["tool_choice"] = {"type": "any" if tool_choice == "required" else "auto"}
    return url, headers, body


def parse_tool_turn(provider: Provider, result: dict) -> ToolTurn:
    try:
        if provider == "openai":
            if result.get("status") in ("failed", "incomplete", "cancelled"):
                logger.warning(
                    "Career tool response did not complete: %s", result["status"]
                )
                raise ValueError
            continuation = result["output"]
        else:
            if result.get("stop_reason") in ("max_tokens", "refusal"):
                raise ValueError
            continuation = result["content"]
        if not isinstance(continuation, list) or not continuation:
            raise ValueError
        calls: list[ToolCall] = []
        text: list[str] = []
        for item in continuation:
            kind = item.get("type")
            if kind == ("function_call" if provider == "openai" else "tool_use"):
                call_id = item["call_id" if provider == "openai" else "id"]
                name = item["name"]
                arguments = (
                    json.loads(item["arguments"])
                    if provider == "openai"
                    else item["input"]
                )
                if (
                    not isinstance(call_id, str)
                    or not call_id
                    or not isinstance(name, str)
                    or not name
                    or not isinstance(arguments, dict)
                    or any(call.id == call_id for call in calls)
                ):
                    raise ValueError
                calls.append(ToolCall(call_id, name, arguments))
            elif provider == "openai" and kind == "message":
                for block in item["content"]:
                    if block.get("type") == "output_text":
                        if not isinstance(block.get("text"), str):
                            raise ValueError
                        text.append(block["text"])
            elif provider == "anthropic" and kind == "text":
                if not isinstance(item.get("text"), str):
                    raise ValueError
                text.append(item["text"])
        output = "".join(text).strip()
        if not calls and not output:
            raise ValueError
        usage = result.get("usage") or {}
        if not isinstance(usage, dict):
            raise ValueError
        return ToolTurn(provider, calls, continuation, output, usage)
    except ValueError, KeyError, TypeError, AttributeError:
        raise ChatError() from None


async def tool_turn(
    config: Generation,
    key: str,
    messages: list[dict],
    instructions: str,
    tools: list[dict],
    *,
    tool_choice: Literal["auto", "required"] = "auto",
) -> ToolTurn:
    url, headers, body = tool_request(
        config, key, messages, instructions, tools, tool_choice=tool_choice
    )
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30, connect=10), follow_redirects=False
        ) as client:
            response = await client.post(url, headers=headers, json=body)
        if response.status_code != 200:
            logger.warning("Career tool request HTTP status=%s", response.status_code)
            raise ChatError()
        turn = parse_tool_turn(config.provider, response.json())
        if tool_choice == "required" and not turn.calls:
            raise ChatError()
        return turn
    except httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError:
        logger.warning("Career tool request or response validation failed")
        raise ChatError() from None


def append_results(
    history: list[dict], turn: ToolTurn, results: dict[str, Any]
) -> list[dict]:
    if set(results) != {call.id for call in turn.calls}:
        raise ValueError("Each tool call needs exactly one result")
    outputs = [
        (call.id, json.dumps(results[call.id], ensure_ascii=False, allow_nan=False))
        for call in turn.calls
    ]
    if turn.provider == "openai":
        return [
            *history,
            *turn.continuation,
            *[
                {"type": "function_call_output", "call_id": call_id, "output": value}
                for call_id, value in outputs
            ],
        ]
    return [
        *history,
        {"role": "assistant", "content": turn.continuation},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": call_id, "content": value}
                for call_id, value in outputs
            ],
        },
    ]


async def complete(config: Generation, key: str, prompt: str, instructions: str) -> str:
    url, headers, body = request(
        config, key, [{"role": "user", "content": prompt}], instructions
    )
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.post(url, headers=headers, json=body)
        if response.status_code != 200:
            raise ChatError()
        result = response.json()
        blocks = (
            [block for item in result["output"] for block in item.get("content", [])]
            if config.provider == "openai"
            else result["content"]
        )
        value = "".join(block.get("text", "") for block in blocks).strip()
        if not value:
            raise ValueError
        return value
    except httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError:
        raise ChatError() from None


async def embed(query: str, config: Embeddings, key: str) -> list[float]:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": config.model,
                    "dimensions": config.dimensions,
                    "encoding_format": "float",
                    "input": [query],
                },
            )
        if response.status_code != 200:
            raise ChatError()
        result = response.json()["data"]
        if len(result) != 1 or result[0]["index"] != 0:
            raise ValueError
        vector = result[0]["embedding"]
        if (
            len(vector) != config.dimensions
            or not all(
                type(value) in (int, float) and math.isfinite(value) for value in vector
            )
            or not any(vector)
        ):
            raise ValueError
        return vector
    except httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError:
        raise ChatError() from None


async def events(lines: AsyncIterator[str]) -> AsyncIterator[dict]:
    data: list[str] = []
    size = 0
    async for line in lines:
        if not line:
            if data:
                value = "\n".join(data)
                if value != "[DONE]":
                    parsed = json.loads(value)
                    if not isinstance(parsed, dict):
                        raise ValueError("Invalid stream event")
                    yield parsed
                data = []
                size = 0
        elif line.startswith("data:"):
            value = line[5:].removeprefix(" ")
            size += len(value)
            if size > 2 * 1024 * 1024:
                raise ValueError("Stream event is too large")
            data.append(value)
    if data:
        raise ValueError("Incomplete stream event")


async def stream(
    config: Generation,
    key: str,
    messages: list[dict[str, str]],
    instructions: str,
    *,
    reasoning_effort: Literal["low"] | None = None,
) -> AsyncIterator[str]:
    url, headers, body = request(
        config,
        key,
        messages,
        instructions,
        streaming=True,
        reasoning_effort=reasoning_effort,
    )
    emitted = False
    try:
        async with (
            httpx.AsyncClient(
                timeout=httpx.Timeout(30, connect=10), follow_redirects=False
            ) as client,
            client.stream("POST", url, headers=headers, json=body) as response,
        ):
            if response.status_code != 200:
                raise ChatError()
            async for event in events(response.aiter_lines()):
                kind = event.get("type")
                if kind in ("error", "response.failed", "response.incomplete"):
                    raise ChatError(INTERRUPTED, 502)
                if config.provider == "openai":
                    value = (
                        event.get("delta")
                        if kind == "response.output_text.delta"
                        else None
                    )
                    finished = kind == "response.completed"
                else:
                    delta = event.get("delta", {})
                    value = (
                        delta.get("text")
                        if kind == "content_block_delta"
                        and delta.get("type") == "text_delta"
                        else None
                    )
                    if (
                        kind == "message_delta"
                        and delta.get("stop_reason") == "max_tokens"
                    ):
                        raise ChatError(INTERRUPTED, 502)
                    finished = kind == "message_stop"
                if value is not None:
                    if not isinstance(value, str):
                        raise ValueError("Invalid text delta")
                    if value:
                        emitted = True
                        yield value
                if finished:
                    if not emitted:
                        raise ChatError(INTERRUPTED, 502)
                    return
        raise ChatError(INTERRUPTED, 502)
    except httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError:
        raise ChatError(INTERRUPTED, 502) from None
