from collections.abc import Iterator

import pytest

from app.core.config import get_settings
from app.db import get_engine


@pytest.fixture(autouse=True)
def settings_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key, value in {
        "POSTGRES_HOST": "db",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "test",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
