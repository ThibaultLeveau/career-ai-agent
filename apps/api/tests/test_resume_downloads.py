import os
from urllib.parse import quote

import pytest
from sqlalchemy.exc import OperationalError

from app.api import public
from app.chat import components
from app.content.models import Document
from app.content.resume_download import download_document_id, download_token

database = pytest.mark.skipif(
    not os.environ.get("TEST_ADMIN_DB"),
    reason="Run scripts/check.sh for PostgreSQL tests",
)


def test_resume_tokens_are_authenticated_and_purpose_separated():
    token = download_token(42)
    assert download_document_id(token) == 42
    for invalid in (
        "",
        token[:-10] + "tampered!!",
        "x" * 2049,
        components.seal(components.DetailScope(entity="projects", id=42)),
        components.seal(components.ListScope(entity="jobs", ids=[42], page_size=5)),
    ):
        with pytest.raises(ValueError):
            download_document_id(invalid)
    with pytest.raises(components.ComponentError):
        components.unseal(token, components.DetailScope)


@pytest.fixture
def resume(db):
    content = b"%PDF-1.7\ncurrent resume bytes"
    record = Document(
        title="Engineering resume",
        filename="R\u00e9sum\u00e9 Thibault.pdf",
        size=len(content),
        content=content,
        document_type_key="resume",
        available_in_chat=True,
    )
    db.add(record)
    db.flush()
    return record


@database
def test_public_resume_download_uses_current_pdf_and_safe_headers(client, db, resume):
    client.headers.pop("origin", None)
    token = download_token(resume.id)
    response = client.get("/public/resumes/download", params={"token": token})
    assert response.status_code == 200
    assert response.content == resume.content
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''" + quote(resume.filename, safe="")
    )
    resume.content = b"%PDF-1.7\nreplacement bytes"
    resume.size = len(resume.content)
    resume.filename = "Updated resume.pdf"
    db.flush()
    updated = client.get("/public/resumes/download", params={"token": token})
    assert updated.content == resume.content
    assert "Updated%20resume.pdf" in updated.headers["content-disposition"]
    assert client.get(f"/admin/documents/{resume.id}/file").status_code == 401


@database
def test_public_resume_revocation_and_unpublished_documents(client, db, resume):
    token = download_token(resume.id)
    resume.available_in_chat = False
    db.flush()
    assert (
        client.get("/public/resumes/download", params={"token": token}).status_code
        == 404
    )
    resume.document_type_key = "other"
    db.flush()
    assert (
        client.get("/public/resumes/download", params={"token": token}).status_code
        == 404
    )
    db.delete(resume)
    db.flush()
    assert (
        client.get("/public/resumes/download", params={"token": token}).status_code
        == 404
    )
    assert (
        client.get(
            "/public/resumes/download", params={"token": download_token(99999999)}
        ).status_code
        == 404
    )
    assert client.get("/public/documents").status_code == 404


@database
def test_invalid_tokens_do_not_reveal_document_metadata(client, resume):
    for token in (
        "not-a-token",
        components.seal(components.DetailScope(entity="jobs", id=resume.id)),
    ):
        response = client.get("/public/resumes/download", params={"token": token})
        assert response.status_code == 404
        assert resume.title not in response.text
        assert response.headers["cache-control"] == "no-store"


@database
def test_download_database_errors_remain_retryable_and_private(client, monkeypatch):
    def unavailable(*args):
        raise OperationalError("private statement", {}, Exception("private error"))

    monkeypatch.setattr(public, "eligible_resume", unavailable)
    response = client.get(
        "/public/resumes/download", params={"token": download_token(1)}
    )
    assert response.status_code == 503
    assert "private" not in response.text
    assert response.headers["cache-control"] == "no-store"
