import json
import math
from collections.abc import AsyncIterator

import httpx

from app.admin.schemas import Embeddings, Generation

UNAVAILABLE = (
    "The career assistant is temporarily unavailable. Please try again shortly."
)
INTERRUPTED = "The reply was interrupted. Please try again."


class ChatError(Exception):
    def __init__(self, message: str = UNAVAILABLE, status: int = 503):
        super().__init__(message)
        self.status = status


def request(
    config: Generation,
    key: str,
    messages: list[dict[str, str]],
    instructions: str,
    *,
    streaming: bool = False,
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
) -> AsyncIterator[str]:
    url, headers, body = request(config, key, messages, instructions, streaming=True)
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
