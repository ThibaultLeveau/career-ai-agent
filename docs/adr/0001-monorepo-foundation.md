# 0001: Monorepo foundation

- Status: Accepted
- Date: 2026-10-23

## Context

The portfolio needs an easily cloned foundation for Python API development, a TypeScript frontend, and future vector-backed capabilities. Initialization must remain small and contain no business features or RAG.

## Decision

Use separate `apps/api` and `apps/web` projects with uv and npm lockfiles. Use FastAPI with synchronous SQLAlchemy and psycopg, Alembic migrations, Next.js App Router with strict TypeScript and Tailwind, and PostgreSQL with pgvector.

Docker Compose is the default installation path. Built application images are the default; an explicitly selected development override enables hot reload. The database uses a persistent named volume. A one-shot service applies migrations after database readiness and before API startup.

Use modular configuration, routing, and database wiring; introduce feature modules when features exist. Keep documentation in Markdown and validate the scaffold through one shared local/CI script.

## Consequences

A clone can run without host language toolchains. App dependency and image updates must preserve the lockfiles and pass both development checks and production container validation. Source-only mounts avoid dependency volume drift but require rebuilding after dependency or configuration changes.

Synchronous sessions minimize initial plumbing; asynchronous database access can be revisited with a concrete workload. PostgreSQL-specific integration checks use real PostgreSQL rather than SQLite. Public deployment infrastructure and application capabilities remain separate work.
