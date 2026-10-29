import json
import os
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.admin import providers
from app.admin.models import RagConfiguration
from app.admin.schemas import (
    ConnectionTest,
    RagSettings,
    SettingsPatch,
    agent_generation,
)
from app.chat.agent_prompts import DEFAULT_AGENT_PROMPTS

database = pytest.mark.skipif(
    not os.environ.get("TEST_ADMIN_DB"), reason="Requires PostgreSQL"
)


def test_legacy_settings_default_to_disabled_agents_and_independent_prompts():
    settings = RagSettings.model_validate({"chat": {"model": "existing-model"}})
    assert settings.agents.enabled is False
    for role, prompt in DEFAULT_AGENT_PROMPTS.items():
        assert getattr(settings.agents, role).prompt == prompt
        assert getattr(settings.agents, role).generation is None
        assert agent_generation(settings, role).model == "existing-model"
    settings.agents.database.prompt = "Custom database prompt"
    assert RagSettings().agents.database.prompt == DEFAULT_AGENT_PROMPTS["database"]
    assert SettingsPatch(agents=settings.agents).agents == settings.agents


def test_agent_generation_overrides_and_null_restore_chat_inheritance():
    settings = RagSettings(
        chat={
            "provider": "anthropic",
            "model": "chat-model",
            "max_output_tokens": 3000,
        },
        agents={
            "database": {
                "prompt": "Find evidence",
                "generation": {
                    "provider": "openai",
                    "model": "database-model",
                    "max_output_tokens": 900,
                },
            }
        },
    )
    override = agent_generation(settings, "database")
    assert (override.provider, override.model, override.max_output_tokens) == (
        "openai",
        "database-model",
        900,
    )
    settings.agents.database.generation = None
    inherited = agent_generation(settings, "database")
    assert (inherited.provider, inherited.model, inherited.max_output_tokens) == (
        "anthropic",
        "chat-model",
        3000,
    )


@pytest.mark.parametrize(
    "role",
    [
        {"prompt": "x" * 16001},
        {"prompt": "valid", "generation": {"provider": "other"}},
        {"prompt": "valid", "generation": {"max_output_tokens": 127}},
        {"prompt": "valid", "tools": ["raw_sql"]},
    ],
)
def test_agent_configuration_validates_prompts_models_and_unknown_fields(role):
    with pytest.raises(ValidationError):
        RagSettings(agents={"database": role})


def result_for(provider, tool=True):
    if provider == "openai":
        return {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "probe-1",
                    "name": "capability_probe",
                    "arguments": '{"value":"OK"}',
                }
                if tool
                else {"type": "message", "content": [{"text": "OK"}]}
            ]
        }
    return {
        "content": [
            {
                "type": "tool_use",
                "id": "probe-1",
                "name": "capability_probe",
                "input": {"value": "OK"},
            }
            if tool
            else {"type": "text", "text": "OK"}
        ]
    }


def fake_client(monkeypatch, provider_result):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.return_value = httpx.Response(200, json=provider_result)
    monkeypatch.setattr(providers.httpx, "Client", Mock(return_value=client))
    return client


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("role", DEFAULT_AGENT_PROMPTS)
def test_role_capability_checks_use_draft_override_and_native_tools(
    monkeypatch, provider, role
):
    needs_tools = True
    result = result_for(provider, needs_tools)
    if role == "database":
        from app.chat.query_catalog import catalog

        if provider == "openai":
            result["output"][0]["name"] = "query_database"
            result["output"][0]["arguments"] = json.dumps(catalog()["example"])
        else:
            result["content"][0]["name"] = "query_database"
            result["content"][0]["input"] = catalog()["example"]
    client = fake_client(monkeypatch, result)
    data = ConnectionTest(
        settings={
            "chat": {"model": "inherited-model"},
            "agents": {
                role: {
                    "prompt": "Draft role instructions",
                    "generation": {"provider": provider, "model": "draft-model"},
                }
            },
        },
        key="draft-private-key",
    )
    db = Mock()
    result = providers.test_connection(role, data, db)
    assert result.ok and "private" not in result.message
    db.get.assert_not_called()
    db.commit.assert_not_called()
    body = client.post.call_args.kwargs["json"]
    assert body["model"] == "draft-model"
    assert body["instructions" if provider == "openai" else "system"] == (
        "Draft role instructions"
    )
    assert bool(body.get("tools")) == needs_tools
    if needs_tools:
        assert body["tool_choice"] == (
            "required" if provider == "openai" else {"type": "any"}
        )


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_tool_capability_check_rejects_text_only_response(monkeypatch, provider):
    fake_client(monkeypatch, result_for(provider, False))
    data = ConnectionTest(
        settings={"chat": {"provider": provider, "model": "inherited-model"}},
        key="draft-key",
    )
    with pytest.raises(HTTPException) as error:
        providers.test_connection("database", data, Mock())
    assert error.value.status_code == 502
    assert "capability test did not pass" in error.value.detail


@database
def test_agent_settings_roundtrip_is_admin_only_and_reversible(client, db):
    assert (
        client.patch("/admin/settings", json={"agents": {"enabled": True}}).status_code
        == 401
    )
    assert (
        client.post(
            "/admin/test/database", json={"settings": {}, "key": "draft-key"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/admin/login",
            json={"username": "owner", "password": "initial-test-password"},
        ).status_code
        == 200
    )
    before = client.get("/admin/settings").json()
    agents = before["agents"]
    agents["enabled"] = True
    agents["database"]["prompt"] = "A customized database prompt"
    agents["rag"]["generation"] = {
        "provider": "anthropic",
        "model": "chosen",
        "max_output_tokens": 2048,
    }
    saved = client.patch("/admin/settings", json={"agents": agents})
    assert saved.status_code == 200 and saved.json()["agents"] == agents
    assert saved.json()["chat"] == before["chat"]
    assert client.get("/admin/settings").json()["agents"] == agents
    assert db.get(RagConfiguration, 1).configuration["agents"] == agents
    agents["enabled"] = False
    agents["rag"]["generation"] = None
    assert (
        client.patch("/admin/settings", json={"agents": agents}).json()["agents"]
        == agents
    )
