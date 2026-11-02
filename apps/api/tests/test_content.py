import os
from urllib.parse import unquote

import pytest
from sqlalchemy import func, inspect, select

from app.content.models import Document
from app.ingestion.models import IngestionJob, Source

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_ADMIN_DB"),
    reason="Run scripts/check.sh for PostgreSQL tests",
)
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


@pytest.fixture
def signed_in(client):
    assert (
        client.post(
            "/admin/login",
            json={"username": "owner", "password": "initial-test-password"},
        ).status_code
        == 200
    )
    return client


def create(client, path, data):
    response = client.post(f"/admin/{path}", json=data)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("resource", ["jobs", "projects", "skills", "documents"])
def test_content_authentication_and_origin(client, signed_in, resource):
    assert client.get(f"/admin/{resource}").status_code == 200
    assert (
        client.delete(
            f"/admin/{resource}/1", headers={"Origin": "https://other.test"}
        ).status_code
        == 403
    )
    client.cookies.clear()
    for method, path, options in [
        ("GET", resource, {}),
        ("GET", f"{resource}/1", {}),
        ("DELETE", f"{resource}/1", {}),
        (
            "POST",
            resource,
            {"json": {}}
            if resource != "documents"
            else {
                "data": {"title": "Resume"},
                "files": {"file": ("resume.pdf", PDF, "application/pdf")},
            },
        ),
        (
            "PUT",
            f"{resource}/1",
            {"json": {}} if resource != "documents" else {"data": {"title": "Resume"}},
        ),
    ]:
        response = client.request(method, f"/admin/{path}", **options)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
    if resource == "documents":
        assert client.get("/admin/documents/1/file").status_code == 401


def test_jobs_projects_skills_lifecycle(signed_in):
    client = signed_in
    job = create(
        client,
        "jobs",
        {
            "title": " Engineer ",
            "company": "Acme",
            "start_month": "2020-02",
            "ongoing": True,
            "summary": "Build products",
            "responsibilities": "Lead delivery",
            "achievements": "Reduced latency",
        },
    )
    assert job["title"] == "Engineer" and job["project_count"] == 0
    assert job["created_at"] and job["updated_at"]
    skill = create(client, "skills", {"keyword": " Python "})
    assert skill["keyword"] == "Python"
    for keyword in ("python", " PYTHON "):
        assert (
            client.post("/admin/skills", json={"keyword": keyword}).status_code == 409
        )
    project = create(
        client,
        "projects",
        {
            "name": "Search",
            "job_id": job["id"],
            "skill_ids": [skill["id"], skill["id"]],
            "website_url": "https://example.com",
            "outcomes": "Faster discovery",
        },
    )
    assert project["kind"] == "professional" and len(project["skills"]) == 1
    assert client.get(f"/admin/jobs/{job['id']}").json()["project_count"] == 1
    assert client.delete(f"/admin/jobs/{job['id']}").status_code == 409
    renamed = client.put(f"/admin/skills/{skill['id']}", json={"keyword": "Python 3"})
    assert renamed.status_code == 200
    assert (
        client.get(f"/admin/projects/{project['id']}").json()["skills"][0]["keyword"]
        == "Python 3"
    )
    other = create(client, "jobs", {"title": "Lead", "company": "Other"})
    moved = client.put(
        f"/admin/projects/{project['id']}",
        json={"name": "Search", "job_id": other["id"], "skill_ids": [skill["id"]]},
    )
    assert moved.json()["job_id"] == other["id"]
    assert client.delete(f"/admin/jobs/{job['id']}").status_code == 204
    assert client.delete(f"/admin/skills/{skill['id']}").status_code == 204
    assert client.get(f"/admin/projects/{project['id']}").json()["skills"] == []
    updated = client.put(
        f"/admin/projects/{project['id']}", json={"name": "Personal search"}
    ).json()
    assert updated["kind"] == "personal" and updated["job_id"] is None
    assert client.delete(f"/admin/jobs/{other['id']}").status_code == 204
    assert client.get("/admin/projects").json()[0]["name"] == "Personal search"
    assert client.delete(f"/admin/projects/{project['id']}").status_code == 204
    assert client.get(f"/admin/projects/{project['id']}").status_code == 404


@pytest.mark.parametrize(
    "path,data",
    [
        ("jobs", {"title": " ", "company": "Acme"}),
        ("jobs", {"title": "Dev", "company": ""}),
        (
            "jobs",
            {
                "title": "Dev",
                "company": "Acme",
                "start_month": "2025-02",
                "end_month": "2024-12",
            },
        ),
        ("jobs", {"title": "Dev", "company": "Acme", "start_month": "2025-13"}),
        (
            "jobs",
            {
                "title": "Dev",
                "company": "Acme",
                "ongoing": True,
                "end_month": "2025-12",
            },
        ),
        ("projects", {"name": ""}),
        ("projects", {"name": "Demo", "website_url": "javascript:alert(1)"}),
        ("projects", {"name": "Demo", "repository_url": "ftp://example.com"}),
        ("projects", {"name": "Demo", "job_id": 999999}),
        ("projects", {"name": "Demo", "skill_ids": [999999]}),
        ("projects", {"name": "Demo", "kind": "professional"}),
        ("skills", {"keyword": " "}),
    ],
)
def test_content_validation(signed_in, path, data):
    assert signed_in.post(f"/admin/{path}", json=data).status_code == 422
    assert signed_in.get(f"/admin/{path}").json() == []


@pytest.mark.parametrize("resource", ["jobs", "projects", "skills", "documents"])
def test_missing_records(signed_in, resource):
    assert signed_in.get(f"/admin/{resource}/999999").status_code == 404
    assert signed_in.delete(f"/admin/{resource}/999999").status_code == 404


def test_job_update_and_skill_rename_conflict(signed_in):
    client = signed_in
    job = create(client, "jobs", {"title": "Engineer", "company": "Acme"})
    response = client.put(
        f"/admin/jobs/{job['id']}",
        json={
            "title": "Senior engineer",
            "company": "Acme",
            "start_month": "2020-01",
            "end_month": "2024-12",
            "location": "Paris",
            "summary": "Summary",
            "responsibilities": "Delivery",
            "achievements": "Impact",
        },
    )
    assert response.status_code == 200
    assert client.get(f"/admin/jobs/{job['id']}").json()["achievements"] == "Impact"
    create(client, "skills", {"keyword": "Python"})
    skill = create(client, "skills", {"keyword": "SQL"})
    assert (
        client.put(
            f"/admin/skills/{skill['id']}", json={"keyword": " PYTHON "}
        ).status_code
        == 409
    )
    assert client.get(f"/admin/skills/{skill['id']}").json()["keyword"] == "SQL"


def test_document_roundtrip_replacement_and_deletion(signed_in, db):
    client = signed_in
    response = client.post(
        "/admin/documents",
        data={"title": "Resume"},
        files={"file": ("../../résumé.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["filename"] == "résumé.pdf" and doc["size"] == len(PDF)
    assert doc["document_type_key"] == "other"
    assert doc["document_type_name"] == "Other"
    assert doc["available_in_chat"] is False
    assert doc["matching_notes"] == ""
    assert "content" not in doc
    db.expunge_all()
    stored = db.scalar(select(Document))
    assert "content" in inspect(stored).unloaded
    path = f"/admin/documents/{doc['id']}"
    download = client.get(f"{path}/file")
    assert download.content == PDF
    assert download.headers["content-type"] == "application/pdf"
    assert "résumé.pdf" in unquote(download.headers["content-disposition"])
    assert download.headers["cache-control"] == "no-store"
    assert client.put(path, data={"title": "English resume"}).status_code == 200
    assert client.get(f"{path}/file").content == PDF
    assert (
        client.put(
            path,
            data={"title": "Bad replacement"},
            files={"file": ("bad.pdf", b"not a PDF", "application/pdf")},
        ).status_code
        == 422
    )
    assert client.get(path).json()["title"] == "English resume"
    assert client.get(f"{path}/file").content == PDF
    replacement = PDF + b"\n% second version"
    assert (
        client.put(
            path,
            data={"title": "New resume"},
            files={"file": ("new.pdf", replacement, "application/pdf")},
        ).status_code
        == 200
    )
    assert client.get(f"{path}/file").content == replacement
    assert client.get("/admin/documents").json()[0]["filename"] == "new.pdf"
    assert client.delete(path).status_code == 204
    assert client.get(f"{path}/file").status_code == 404


@pytest.mark.parametrize(
    "filename,content,mime,status",
    [
        ("resume.txt", PDF, "application/pdf", 422),
        ("resume.pdf", PDF, "text/plain", 422),
        ("resume.pdf", b"", "application/pdf", 422),
        ("resume.pdf", b"invalid", "application/pdf", 422),
        ("resume.pdf", b"%PDF-" + b"x" * (10 * 1024 * 1024), "application/pdf", 413),
        ("resume.pdf", b"%PDF-" + b"x" * (11 * 1024 * 1024), "application/pdf", 413),
    ],
)
def test_invalid_documents(signed_in, filename, content, mime, status):
    response = signed_in.post(
        "/admin/documents",
        data={"title": "Resume"},
        files={"file": (filename, content, mime)},
    )
    assert response.status_code == status
    assert signed_in.get("/admin/documents").json() == []


def test_document_boundary_size_and_required_fields(signed_in):
    client = signed_in
    exact = PDF + b"x" * (10 * 1024 * 1024 - len(PDF))
    response = client.post(
        "/admin/documents",
        data={"title": "Resume"},
        files={"file": ("resume.pdf", exact, "application/pdf")},
    )
    assert response.status_code == 201
    assert client.get(f"/admin/documents/{response.json()['id']}/file").content == exact
    assert client.post("/admin/documents", data={"title": "Resume"}).status_code == 422
    assert (
        client.post(
            "/admin/documents",
            data={"title": " "},
            files={"file": ("resume.pdf", PDF, "application/pdf")},
        ).status_code
        == 422
    )


def test_document_type_catalog_access_and_additions(client, signed_in):
    types = client.get("/admin/document-types").json()
    assert types == [
        {"key": "other", "name": "Other", "is_builtin": True},
        {"key": "resume", "name": "Resume", "is_builtin": True},
    ]
    assert (
        client.post(
            "/admin/document-types",
            json={"name": "Certificate"},
            headers={"Origin": "https://other.test"},
        ).status_code
        == 403
    )
    created = client.post("/admin/document-types", json={"name": " Certificate "})
    assert created.status_code == 201
    custom = created.json()
    assert custom["name"] == "Certificate"
    assert custom["is_builtin"] is False
    assert custom["key"].startswith("certificate-")
    assert custom in client.get("/admin/document-types").json()
    for name in ("certificate", " CERTIFICATE ", "Resume", " other "):
        assert (
            client.post("/admin/document-types", json={"name": name}).status_code == 409
        )
    for body in ({"name": " "}, {"name": "x" * 101}, {"name": "CV", "key": "resume"}):
        assert client.post("/admin/document-types", json=body).status_code == 422
    client.cookies.clear()
    assert client.get("/admin/document-types").status_code == 401
    assert (
        client.post("/admin/document-types", json={"name": "Letter"}).status_code == 401
    )


def test_document_types_sharing_and_metadata_do_not_reingest(signed_in, db):
    client = signed_in
    custom = create(client, "document-types", {"name": "Certificate"})
    response = client.post(
        "/admin/documents",
        data={"title": "Backend resume", "document_type_key": "resume"},
        files={"file": ("resume.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 201
    document = response.json()
    assert document["document_type_name"] == "Resume"
    assert document["available_in_chat"] is False
    path = f"/admin/documents/{document['id']}"
    source = db.scalar(select(Source).where(Source.record_id == document["id"]))
    initial_revision = source.revision
    initial_jobs = db.scalar(select(func.count()).select_from(IngestionJob))
    enabled = client.put(
        path,
        data={
            "title": "Backend resume",
            "available_in_chat": "true",
            "matching_notes": " English, senior backend roles ",
        },
    )
    assert enabled.status_code == 200
    assert enabled.json()["available_in_chat"] is True
    assert enabled.json()["matching_notes"] == "English, senior backend roles"
    omitted = client.put(path, data={"title": "Backend resume"}).json()
    assert omitted["available_in_chat"] is True
    assert omitted["document_type_key"] == "resume"
    assert omitted["matching_notes"] == "English, senior backend roles"
    cleared = client.put(
        path, data={"title": "Backend resume", "matching_notes": ""}
    ).json()
    assert cleared["matching_notes"] == ""
    retyped = client.put(
        path,
        data={"title": "Backend resume", "document_type_key": custom["key"]},
    ).json()
    assert retyped["document_type_name"] == "Certificate"
    assert retyped["available_in_chat"] is False
    resumed = client.put(
        path, data={"title": "Backend resume", "document_type_key": "resume"}
    ).json()
    assert resumed["available_in_chat"] is False
    db.refresh(source)
    assert source.revision == initial_revision
    assert db.scalar(select(func.count()).select_from(IngestionJob)) == initial_jobs
    assert client.get(f"{path}/file").content == PDF
    assert client.put(path, data={"title": "Updated backend resume"}).status_code == 200
    db.refresh(source)
    assert source.revision == initial_revision + 1


def test_document_explicit_resume_selection_can_enable_sharing(signed_in):
    client = signed_in
    document = client.post(
        "/admin/documents",
        data={"title": "Resume"},
        files={"file": ("resume.pdf", PDF, "application/pdf")},
    ).json()
    enabled = client.put(
        f"/admin/documents/{document['id']}",
        data={
            "title": "Resume",
            "document_type_key": "resume",
            "available_in_chat": "true",
        },
    )
    assert enabled.status_code == 200
    assert enabled.json()["available_in_chat"] is True


@pytest.mark.parametrize(
    "fields",
    [
        {"document_type_key": "missing"},
        {"available_in_chat": "true"},
        {"matching_notes": "x" * 2001},
        {"available_in_chat": "invalid"},
    ],
)
def test_invalid_document_metadata(signed_in, fields):
    response = signed_in.post(
        "/admin/documents",
        data={"title": "Resume", **fields},
        files={"file": ("resume.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 422
    assert signed_in.get("/admin/documents").json() == []
