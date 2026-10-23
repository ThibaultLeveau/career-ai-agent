import os
from collections.abc import Iterator

import pytest

from app.core.config import get_settings
from app.db import get_engine


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
