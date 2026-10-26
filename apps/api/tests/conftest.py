import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.admin.models import Administrator, AdminSession, ProviderKey, RagConfiguration
from app.bootstrap import bootstrap
from app.core.config import get_settings
from app.db import get_engine, get_session
from app.main import app


@pytest.fixture(autouse=True)
def settings_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    environment = {
        "POSTGRES_HOST": "db",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "test",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
    }
    if os.environ.get("TEST_ADMIN_DB"):
        environment = {}
    environment.update(
        {
            "APP_ORIGIN": "http://testserver",
            "ADMIN_INITIAL_USERNAME": "owner",
            "ADMIN_INITIAL_PASSWORD": "initial-test-password",
            "SETTINGS_ENCRYPTION_KEY": "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg=",
        }
    )
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()


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
