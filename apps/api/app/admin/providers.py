import json

import httpx
from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.admin.models import ProviderKey
from app.admin.schemas import ConnectionTest, Stage, TestResult
from app.admin.security import cipher


def test_connection(stage: Stage, data: ConnectionTest, db: Session) -> TestResult:
    settings = getattr(data.settings, stage)
    key = data.key.get_secret_value() if data.key else None
    if not key:
        saved = db.get(ProviderKey, settings.provider)
        if not saved:
            raise HTTPException(422, "Add an API key for this provider first")
        try:
            key = cipher().decrypt(saved.encrypted_key.encode()).decode()
        except InvalidToken, ValueError:
            raise HTTPException(503, "The saved key could not be decrypted") from None
    if not settings.model:
        raise HTTPException(422, "Choose a model before testing")

    prompt = "Reply with the single word OK."
    if stage == "reranking":
        prompt = (
            'Rank these passages for the query "Python programming". '
            "Return only a JSON array containing both passage IDs, best match first. "
            "Passage 1: Growing tomatoes. Passage 2: Writing Python software."
        )
    if stage == "embeddings":
        url = "https://api.openai.com/v1/embeddings"
        headers = {"Authorization": f"Bearer {key}"}
        body = {
            "model": settings.model,
            "input": "Career AI connection test",
            "dimensions": settings.dimensions,
        }
    elif settings.provider == "openai":
        url = "https://api.openai.com/v1/responses"
        headers = {"Authorization": f"Bearer {key}"}
        body = {
            "model": settings.model,
            "input": prompt,
            "max_output_tokens": min(settings.max_output_tokens, 2048),
            "store": False,
        }
        if stage == "chat" and settings.system_prompt:
            body["instructions"] = settings.system_prompt
    else:
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        body = {
            "model": settings.model,
            "max_tokens": min(settings.max_output_tokens, 2048),
            "messages": [{"role": "user", "content": prompt}],
        }
        if stage == "chat" and settings.system_prompt:
            body["system"] = settings.system_prompt
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        raise HTTPException(504, "The provider timed out. Try again.") from None
    except httpx.HTTPError, ValueError:
        raise HTTPException(502, "Could not connect to the provider") from None
    if response.status_code != 200:
        message = {
            400: "The provider rejected this model or its settings",
            401: "The provider rejected the API key",
            403: "This API key does not have access to the selected model",
            404: "The selected model is unavailable for this API key",
            429: "Provider rate limit or quota reached. Try again later.",
        }.get(response.status_code, "The provider is unavailable. Try again later.")
        raise HTTPException(502, message)
    try:
        result = response.json()
        if stage == "embeddings":
            vector = result["data"][0]["embedding"]
            if len(vector) != settings.dimensions or not all(
                isinstance(n, (float, int)) for n in vector
            ):
                raise ValueError
        else:
            blocks = (
                [b for item in result["output"] for b in item.get("content", [])]
                if settings.provider == "openai"
                else result["content"]
            )
            output = "".join(b.get("text", "") for b in blocks).strip()
            if not output:
                raise ValueError
            if stage == "reranking":
                ranking = json.loads(output.removeprefix("```json").removesuffix("```"))
                if ranking != [2, 1]:
                    raise ValueError
    except AttributeError, KeyError, IndexError, TypeError, ValueError:
        raise HTTPException(
            502, "The provider responded, but the capability test did not pass"
        ) from None
    return TestResult(message="Connection and model test passed")
