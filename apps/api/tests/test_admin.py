import os
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.admin.models import Administrator, AdminSession, ProviderKey, RagConfiguration
from app.admin.security import cipher, digest, matches
from app.bootstrap import bootstrap
from app.core.config import get_settings
from app.db import get_engine, get_session
from app.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_ADMIN_DB"),
    reason="Run scripts/check.sh for PostgreSQL tests",
)


@pytest.fixture
def db():
    with get_engine().connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            for model in (AdminSession, ProviderKey, RagConfiguration, Administrator):
                session.execute(delete(model))
            bootstrap(session)
            yield session
        transaction.rollback()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        yield client
    app.dependency_overrides.clear()


def sign_in(client, username="owner", password="initial-test-password"):
    response = client.post(
        "/admin/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response


def test_bootstrap_preserves_changed_credentials_and_settings(db, monkeypatch):
    administrator = db.get(Administrator, 1)
    administrator.username = "changed"
    saved = db.get(RagConfiguration, 1)
    saved.configuration = {"chat": {"model": "chosen-model"}}
    db.commit()
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "")
    monkeypatch.setenv("ADMIN_INITIAL_USERNAME", "")
    get_settings.cache_clear()
    bootstrap(db)
    assert db.get(Administrator, 1).username == "changed"
    assert matches(administrator.password_hash, "initial-test-password")
    assert db.get(RagConfiguration, 1).configuration["chat"]["model"] == "chosen-model"


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "session", None),
        ("GET", "settings", None),
        ("GET", "providers", None),
        ("PUT", "settings", {}),
        ("PUT", "providers/openai", {"key": "secret"}),
        ("DELETE", "providers/openai", None),
        ("POST", "test/chat", {"settings": {}}),
        ("PUT", "credentials", {"username": "owner", "current_password": "test"}),
    ],
)
def test_api_requires_authentication(client, method, path, body):
    response = client.request(method, f"/admin/{path}", json=body)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_login_cookie_expiry_logout_and_revocation(client, db):
    response = sign_in(client)
    cookie = response.headers["set-cookie"]
    assert (
        "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=43200" in cookie
    )
    token = client.cookies["career_admin"]
    stored = db.get(AdminSession, digest(token))
    assert stored and stored.token_hash != token
    assert client.get("/admin/session").json() == {"username": "owner"}
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.get("/admin/session").status_code == 401
    sign_in(client)
    token = client.cookies["career_admin"]
    assert client.post("/admin/logout").status_code == 204
    assert db.get(AdminSession, digest(token)) is None
    assert client.get("/admin/session").status_code == 401


def test_login_throttling_and_origin_checks(client, db):
    for _ in range(5):
        response = client.post(
            "/admin/login", json={"username": "wrong", "password": "wrong"}
        )
        assert response.status_code == 401
    assert (
        client.post(
            "/admin/login",
            json={"username": "owner", "password": "initial-test-password"},
        ).status_code
        == 429
    )
    db.get(Administrator, 1).login_window = datetime.now(UTC) - timedelta(minutes=16)
    db.commit()
    sign_in(client)
    for origin in ("https://attacker.example", ""):
        assert (
            client.put(
                "/admin/settings", json={}, headers={"Origin": origin}
            ).status_code
            == 403
        )


def test_credential_change_revokes_every_session(client, db):
    sign_in(client)
    first_token = client.cookies["career_admin"]
    sign_in(client)
    data = {
        "username": "new-owner",
        "current_password": "wrong",
        "new_password": "new-strong-password",
    }
    assert client.put("/admin/credentials", json=data).status_code == 400
    data["current_password"] = "initial-test-password"
    assert client.put("/admin/credentials", json=data).status_code == 204
    assert not list(db.scalars(select(AdminSession)))
    assert (
        client.get(
            "/admin/session", headers={"Cookie": f"career_admin={first_token}"}
        ).status_code
        == 401
    )
    sign_in(client, "new-owner", "new-strong-password")


def test_keys_are_encrypted_write_only_and_removable(client, db):
    sign_in(client)
    key = "sk-private-provider-key"
    assert client.put("/admin/providers/openai", json={"key": key}).status_code == 204
    stored = db.get(ProviderKey, "openai").encrypted_key
    assert key not in stored
    assert cipher().decrypt(stored.encode()).decode() == key
    response = client.get("/admin/providers")
    assert key not in response.text and stored not in response.text
    assert response.json()[0] == {"provider": "openai", "configured": True}
    assert client.delete("/admin/providers/openai").status_code == 204
    assert client.get("/admin/providers").json()[0]["configured"] is False
    response = client.put(
        "/admin/providers/openai", json={"key": "private secret with spaces"}
    )
    assert response.status_code == 422 and "private secret" not in response.text


def test_settings_roundtrip_and_validation(client):
    sign_in(client)
    data = client.get("/admin/settings").json()
    assert data["reranking"]["enabled"] is False
    data["chat"].update(provider="anthropic", model="claude-haiku-5-5")
    assert client.put("/admin/settings", json=data).json() == data
    assert client.get("/admin/settings").json() == data
    for section, change in [
        ("chat", {"provider": "other"}),
        ("embeddings", {"provider": "anthropic"}),
        ("embeddings", {"dimensions": 2000}),
        ("retrieval", {"chunk_overlap": 800}),
        ("retrieval", {"context_count": 21}),
    ]:
        invalid = {**data, section: {**data[section], **change}}
        assert client.put("/admin/settings", json=invalid).status_code == 422
    assert client.get("/admin/settings").json() == data


@pytest.mark.parametrize(
    "stage,provider,result",
    [
        ("chat", "openai", {"output": [{"content": [{"text": "OK"}]}]}),
        ("chat", "anthropic", {"content": [{"text": "OK"}]}),
        ("embeddings", "openai", {"data": [{"embedding": [0.1, 0.2, 0.3]}]}),
        ("reranking", "openai", {"output": [{"content": [{"text": "[2,1]"}]}]}),
        ("reranking", "anthropic", {"content": [{"text": "[2,1]"}]}),
    ],
)
def test_provider_calls_use_drafts_without_saving(
    client, db, monkeypatch, stage, provider, result
):
    sign_in(client)
    data = client.get("/admin/settings").json()
    data[stage]["provider"] = provider
    if stage == "embeddings":
        data[stage]["dimensions"] = 3
    else:
        data[stage]["model"] = "test-model"
    provider_client = Mock()
    provider_client.__enter__ = Mock(return_value=provider_client)
    provider_client.__exit__ = Mock(return_value=False)
    provider_client.post.return_value = httpx.Response(200, json=result)
    monkeypatch.setattr(
        "app.admin.providers.httpx.Client", Mock(return_value=provider_client)
    )
    response = client.post(
        f"/admin/test/{stage}", json={"settings": data, "key": "draft-secret"}
    )
    assert response.status_code == 200
    call = provider_client.post.call_args
    assert call.args[0].startswith(
        "https://api.anthropic.com/"
        if provider == "anthropic"
        else "https://api.openai.com/"
    )
    assert "draft-secret" in str(call.kwargs["headers"])
    assert "draft-secret" not in response.text
    assert db.get(ProviderKey, provider) is None
    assert client.get("/admin/settings").json()["chat"]["model"] == ""


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
def test_provider_errors_are_sanitized(client, monkeypatch, status):
    sign_in(client)
    mock = Mock()
    mock.__enter__ = Mock(return_value=mock)
    mock.__exit__ = Mock(return_value=False)
    mock.post.return_value = httpx.Response(
        status, text="private provider response and secret"
    )
    monkeypatch.setattr("app.admin.providers.httpx.Client", Mock(return_value=mock))
    response = client.post(
        "/admin/test/chat",
        json={"settings": {"chat": {"model": "test"}}, "key": "private-key"},
    )
    assert response.status_code == 502
    assert "private" not in response.text


def test_saved_key_and_timeout(client, db, monkeypatch):
    sign_in(client)
    assert (
        client.put("/admin/providers/openai", json={"key": "saved-key"}).status_code
        == 204
    )
    mock = Mock()
    mock.__enter__ = Mock(return_value=mock)
    mock.__exit__ = Mock(return_value=False)
    mock.post.side_effect = httpx.ReadTimeout("secret details")
    monkeypatch.setattr("app.admin.providers.httpx.Client", Mock(return_value=mock))
    response = client.post(
        "/admin/test/chat", json={"settings": {"chat": {"model": "test"}}}
    )
    assert response.status_code == 504
    assert "secret" not in response.text
    assert mock.post.call_args.kwargs["headers"]["Authorization"] == "Bearer saved-key"


def test_secure_cookie(client, monkeypatch):
    monkeypatch.setenv("APP_ORIGIN", "https://testserver")
    get_settings.cache_clear()
    client.headers["Origin"] = "https://testserver"
    response = sign_in(client)
    assert "Secure" in response.headers["set-cookie"]
    assert client.get("/admin/session").status_code == 401


def test_invalid_provider_response_fails_without_echoing_output(client, monkeypatch):
    sign_in(client)
    mock = Mock()
    mock.__enter__ = Mock(return_value=mock)
    mock.__exit__ = Mock(return_value=False)
    mock.post.return_value = httpx.Response(200, json={"output": "private response"})
    monkeypatch.setattr("app.admin.providers.httpx.Client", Mock(return_value=mock))
    response = client.post(
        "/admin/test/chat",
        json={"settings": {"chat": {"model": "test"}}, "key": "private-key"},
    )
    assert response.status_code == 502
    assert "private" not in response.text
