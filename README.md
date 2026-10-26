# Career AI

An AI-powered personal portfolio with a public placeholder homepage and authenticated administration. The admin panel manages account credentials, encrypted OpenAI/Anthropic keys, and RAG configuration with provider connection tests. Jobs, projects, keyword skills, and resume PDFs can be managed in the admin panel. A durable background worker extracts text, chunks content, and stores embeddings. Public retrieval and chat are not implemented yet.

## Quick start

Install Git and Docker Engine or Docker Desktop with Docker Compose v2.20+ and Buildx. No local Python, Node.js, or PostgreSQL installation is required.

```sh
git clone https://github.com/ThibaultLeveau/career-ai-agent.git
cd career-ai-agent
cp .env.example .env
```

Set `ADMIN_INITIAL_USERNAME` and a unique `ADMIN_INITIAL_PASSWORD` (12+ characters) in `.env`. Generate `SETTINGS_ENCRYPTION_KEY` with the following command and copy its output to `.env`:

```sh
docker run --rm python:3.14.9-slim-bookworm python -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
docker compose up --build
```

Open [the portfolio](http://localhost:3000), [API documentation](http://localhost:8000/docs), or [API health](http://localhost:8000/health). Startup downloads dependencies, builds the applications, waits for PostgreSQL, and runs migrations before starting the API.

Open [administration](http://localhost:3000/admin) and sign in with the initial credentials. Startup creates the single account only when absent. Later changes in **Settings → Account & security** are stored in PostgreSQL and never overwritten by `.env`; initial credential variables can be removed after bootstrap. Credential changes require the current password and sign out all sessions.

`APP_ORIGIN` must match the exact browser origin, including the port (default `http://localhost:3000`). For HTTPS deployment, set it to the public HTTPS origin; session cookies then require HTTPS. Keep `SETTINGS_ENCRYPTION_KEY` stable and backed up with the database: replacing it prevents decryption of existing provider keys. Neither provider keys nor this encryption key belong in frontend environment variables.

In **Settings → AI Provider**, save provider keys separately from model settings. OpenAI supports embeddings; both providers support chat and LLM-based reranking. Reranking starts disabled. Models can be selected from suggestions or entered by API ID; availability is checked with **Test**. Tests use current form values, make a small billable request, and never save changes. No provider request is made on Save. Use **Settings → RAG** for retrieval counts and ingestion chunk size, overlap, and retry count. Retrieval counts configure the future retrieval service.

The example credentials are for local development. Set database credentials and host ports in `.env`; this file is ignored by Git. Web/API ports bind to localhost; PostgreSQL is reachable only inside Compose. Changing database credentials after the first run does not update an existing PostgreSQL volume.

## Career content

Use **Jobs**, **Projects**, **Skills**, and **Documents** in the admin sidebar to create, edit, search, and delete career content. Jobs and projects support month/year dates and structured plain-text descriptions. A project linked to a job is professional; otherwise it is personal. Projects can reference multiple skills. Jobs with linked projects cannot be deleted until those projects are reassigned, unlinked, or deleted. Deleting a skill removes its associations and keeps the projects.

Documents accept multiple independent resume PDFs, up to 10 MiB each. Rename, replace, download, or delete them in the private admin workspace. File bytes are stored in PostgreSQL and included in its backups; replacement is atomic. Only authenticated administrators can download files. Saving new or changed jobs, projects, or documents atomically queues background ingestion; provider calls happen in the worker. PDFs require selectable text; OCR and encrypted PDFs are not supported.

Existing installations must run the migration service (`docker compose run --rm migrate`) using the rebuilt API image before starting the updated application. Migration 0004 adds ingestion storage and moves existing chunking values into ingestion settings without changing provider keys or models. Migration 0005 retires standalone skill ingestion: it cancels unfinished skill jobs and removes their derived text/vectors while preserving skills, relationships, history, and logs. Stop the API and worker during this migration, then start the rebuilt services. Back up an existing database before migrating.

## Ingestion

Jobs, projects, and documents show a status icon with a hover/focus tooltip; click it to open ingestion details. Row actions live in the three-dot menu, also available by right-click or Shift+F10. The menu offers **Edit**, **Re-ingest**, and **Delete**, plus **Download** for documents. Re-ingestion is disabled while active. Skills offer Edit and Delete only.

**Home** shows content counts and a funnel of current item states, counting each job, project, and document once. Pending includes never-ingested, queued, outdated, cancelled, or superseded items; ongoing includes processing and retrying. Successful means current content and settings match the completed ingestion. Skills count as content, but not as separate ingestion sources. The authenticated `/admin/overview` endpoint supplies counts, state totals, and whether work is active.

**Ingestion Jobs** shows a dense, paginated table with expandable details and sanitized logs. Historical skill runs remain visible as **Skills (legacy)**. **Re-ingest all** lets you select jobs, projects, and documents; already-active items are skipped. Status polling runs every two seconds during active work and every ten seconds while idle, pausing in hidden tabs without replacing editor drafts.

Each job's structured fields form one source document. Each project combines its fields, linked job title/company, and sorted skill keywords into one document. These complete documents are then split into overlapping chunks and embedded; fields are not embedded independently. Standalone skill keywords are never embedded.

The worker uses a durable PostgreSQL queue, resumes completed embedding batches after interruption, and atomically publishes complete results. Content edits during processing schedule the latest revision; linked job/skill metadata changes refresh affected projects. Failed rebuilds preserve the previous completed embeddings. Deleting content removes its derived text/vectors while keeping operational history.

Chunk sizes and overlap are measured in tokens (defaults 800/100). Transient errors have three additional retries by default, with exponential backoff and provider retry delays. Authentication, billing, invalid settings, and document errors require correction and manual re-ingestion. Embedding-model/dimension and chunking changes mark items out of date without making provider requests; use the re-ingest controls to rebuild them. Retry and retrieval settings do not invalidate embeddings.

To backfill all existing jobs, projects, and documents through the same queue (safe to repeat while jobs are active):

```sh
docker compose exec -T api python -m app.ingestion enqueue --all --reason backfill
```

Follow progress in **Ingestion Jobs** or `docker compose logs -f worker`. The worker's health check monitors its heartbeat. PDF parsing runs in a separate process with time/memory limits. Logs contain stage/error information, not provider keys or document bodies. Source text and vectors remain private in PostgreSQL and are included in backups.

## Structure

```text
apps/
  api/          FastAPI, configuration, SQLAlchemy, Alembic, pytest
  web/          Next.js App Router, TypeScript, Tailwind CSS
docs/
  architecture.md
  adr/          Architecture decisions and template
scripts/
  check.sh      Local and CI validation
```

Python 3.14 and Node.js 24 run in separate images with committed dependency lockfiles. PostgreSQL 18 includes pgvector. Compose runs `db`, a one-shot `migrate` service, `api`, `worker`, and `web`. See [architecture](docs/architecture.md), [ADRs](docs/adr/README.md), and [engineering conventions](AGENTS.md).

## Development

Stop the default stack before switching modes:

```sh
docker compose down
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

Python application changes and frontend source changes reload automatically. Source mounts leave dependencies and generated output inside containers. Rebuild after changing dependencies, lockfiles, or configuration. Do not run both modes simultaneously with the same project name.

To update dependencies using the container toolchains, mount the relevant project at `/workspace` and run as your host user (POSIX shell):

```sh
docker compose -f compose.yaml -f compose.dev.yaml run --rm --no-deps --user "$(id -u):$(id -g)" -e UV_CACHE_DIR=/tmp/uv -e UV_PROJECT_ENVIRONMENT=/tmp/venv -v "$PWD/apps/api:/workspace" -w /workspace api uv add PACKAGE
docker compose -f compose.yaml -f compose.dev.yaml run --rm --no-deps --user "$(id -u):$(id -g)" -e npm_config_cache=/tmp/npm -v "$PWD/apps/web:/workspace" -w /workspace web npm install --package-lock-only PACKAGE
```

Use `uv add --dev` or `npm install --save-dev --package-lock-only` for development dependencies. Commit the manifest and lockfile together, then rebuild.

## Validation

Run the same checks used by GitHub Actions (requires a POSIX shell and curl):

```sh
sh scripts/check.sh
```

This uses an isolated Compose project on ports 18000/13000, validates configuration, runs backend lint/format/tests (including PostgreSQL integration tests) and frontend lint/types, builds production images, runs Chromium browser tests, checks migrations, and verifies database persistence after container recreation. Provider APIs are mocked; no real provider credentials are required. Its temporary database is removed on exit. Set `CHECK_API_PORT` and `CHECK_WEB_PORT` if those ports are occupied. Browser screenshots are written to `apps/web/test-results/` (ignored by Git); the first browser image build downloads Chromium.

For focused checks after building development images:

```sh
docker compose -f compose.yaml -f compose.dev.yaml run --rm --no-deps api pytest
docker compose -f compose.yaml -f compose.dev.yaml run --rm --no-deps api ruff check .
docker compose -f compose.yaml -f compose.dev.yaml run --rm --no-deps api ruff format --check .
docker compose -f compose.yaml -f compose.dev.yaml run --rm --no-deps web npm run lint
docker compose -f compose.yaml -f compose.dev.yaml run --rm --no-deps web npm run typecheck
```

The frontend production build runs as part of its runtime image build. To check hot reload, edit the homepage and refresh; edit a Python application file and check the API logs for a reload.

## Database and migrations

The first migration enables `vector`; the second adds the administrator, revocable sessions, encrypted provider credentials, and RAG settings; the third adds career content and PDF storage; the fourth adds ingestion jobs, logs, text, chunks, and vectors; the fifth retires standalone skill embeddings. Login throttling lives on the singleton administrator record. Alembic imports the domain models so it can discover their metadata.

```sh
docker compose exec api alembic current
docker compose run --rm migrate
docker compose exec db psql -U career_ai -d career_ai
```

Replace the psql user/database if you changed `.env`. In development, create a migration with the host user so the generated file remains editable:

```sh
docker compose -f compose.yaml -f compose.dev.yaml run --rm --user "$(id -u):$(id -g)" migrate alembic revision --autogenerate -m "describe change"
```

Review generated migrations before applying them. Migrations run as a separate service, never during API startup. Run the migration service after adding a revision. Downgrades are explicit maintenance operations; the initial downgrade removes the vector extension and deliberately does not cascade.

## Shutdown and troubleshooting

```sh
docker compose logs -f
docker compose down
```

`down` preserves the named PostgreSQL volume. To permanently delete the local database and start over:

```sh
docker compose down --volumes
docker compose up --build
```

If startup fails, inspect `docker compose logs db migrate api web`. A failed migration prevents API startup. A failed database probe makes `/health` return 503 with no connection details. If ports are occupied, change `API_PORT`/`WEB_PORT` in `.env`.

The default images use production application commands, but this Compose setup is a local foundation. Public deployment, TLS, backups, separate database roles, and hosted secret management belong to later deployment work.
