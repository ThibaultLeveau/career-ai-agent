# 0003: Career content and PDF storage

Status: Accepted

## Decision

Store jobs, projects, keywords, and resume documents in PostgreSQL. A project has an optional job and a many-to-many skill relationship; professional/personal status is derived from the job association. Restrict deletion of jobs with projects. Deleting a skill removes only its associations.

Store PDF bytes in a deferred binary column with document metadata. PDFs are private, limited to 10 MiB, and downloaded through the authenticated admin proxy. Keeping bytes and metadata in one transaction makes replacement atomic and includes resumes in existing database backups. Multipart requests are bounded before parsing, and metadata queries do not load file bytes.

## Consequences

This suits a small personal resume library without a separate storage service or volume. Database backups grow with uploads. Object storage can replace the binary column if volume increases. PDF parsing, embeddings, and retrieval are deferred; stable record IDs, structured text, relationships, and timestamps provide their future source data.
