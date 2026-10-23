from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app


@pytest.mark.parametrize("available", [True, False])
def test_health_reports_database_availability(available: bool) -> None:
    session = Mock(spec=Session)
    if not available:
        session.execute.side_effect = OperationalError(
            "SELECT 1", {}, Exception("private database details")
        )
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.get("/health")
        assert response.status_code == (200 if available else 503)
        assert response.json() == {"status": "ok" if available else "unavailable"}
        session.execute.assert_called_once()
    finally:
        app.dependency_overrides.clear()
