import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from app.ingestion.text import IngestionError


def retry_delay(value: str | None) -> float:
    try:
        delay = float(value)
        return max(0, delay) if math.isfinite(delay) else 0
    except ValueError, TypeError:
        try:
            return max(
                0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            )
        except ValueError, TypeError, OverflowError:
            return 0


def embed(texts: list[str], config: dict, key: str) -> list[list[float]]:
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": config["model"],
                    "dimensions": config["dimensions"],
                    "encoding_format": "float",
                    "input": texts,
                },
            )
    except httpx.HTTPError:
        raise IngestionError(
            "Could not reach OpenAI. The request will be retried.", True
        ) from None
    if response.status_code != 200:
        code = None
        try:
            code = response.json().get("error", {}).get("code")
        except ValueError, AttributeError:
            pass
        if code in (
            "insufficient_quota",
            "billing_hard_limit_reached",
            "credit_balance_exhausted",
        ):
            raise IngestionError(
                "OpenAI quota or credit balance is exhausted. "
                "Check billing, then re-ingest."
            )
        message = {
            400: "OpenAI rejected the embedding settings or input.",
            401: "OpenAI rejected the API key. Update it in AI settings.",
            403: "The API key cannot access this embedding model.",
            404: "The configured embedding model is unavailable.",
            429: "OpenAI temporarily rate-limited ingestion.",
        }.get(response.status_code, "OpenAI could not complete the embedding request.")
        raise IngestionError(
            message,
            response.status_code in (408, 429) or response.status_code >= 500,
            retry_delay(response.headers.get("Retry-After")),
        )
    try:
        data = response.json()["data"]
        if len(data) != len(texts) or sorted(item["index"] for item in data) != list(
            range(len(texts))
        ):
            raise ValueError
        vectors = [
            item["embedding"] for item in sorted(data, key=lambda item: item["index"])
        ]
        for vector in vectors:
            if len(vector) != config["dimensions"] or not all(
                type(value) in (float, int) and math.isfinite(value) for value in vector
            ):
                raise ValueError
        return vectors
    except ValueError, KeyError, IndexError, TypeError, AttributeError:
        raise IngestionError(
            "OpenAI returned invalid embeddings. "
            "Re-ingest after checking the model settings."
        ) from None
