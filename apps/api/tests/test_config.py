import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_password_preserves_url_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "p@ss:/?#%word"
    monkeypatch.setenv("POSTGRES_PASSWORD", password)
    settings = Settings()
    assert settings.database_url.password == password
    assert settings.database_url.drivername == "postgresql+psycopg"
    assert password not in repr(settings)


@pytest.mark.parametrize(
    ("key", "value"),
    [("POSTGRES_PORT", "0"), ("POSTGRES_PORT", "65536"), ("POSTGRES_PASSWORD", "")],
)
def test_invalid_settings_fail_early(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings()


def test_missing_password_fails_early(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD")
    with pytest.raises(ValidationError):
        Settings()
