# Career AI

An AI-powered personal portfolio foundation. This repository currently contains infrastructure, a database-backed API health endpoint, and a placeholder homepage. Portfolio features, authentication, embeddings, and RAG are not implemented.

## Quick start

Install Git and Docker Engine or Docker Desktop with Docker Compose v2.20+ and Buildx. No local Python, Node.js, or PostgreSQL installation is required.

```sh
git clone https://github.com/ThibaultLeveau/career-ai-agent.git
cd career-ai-agent
cp .env.example .env
docker compose up --build
```

Open [the portfolio](http://localhost:3000), [API documentation](http://localhost:8000/docs), or [API health](http://localhost:8000/health). Startup downloads dependencies, builds the applications, waits for PostgreSQL, and runs migrations before starting the API.

The example credentials are for local development. Set database credentials and host ports in `.env`; this file is ignored by Git. Web/API ports bind to localhost; PostgreSQL is reachable only inside Compose. Changing database credentials after the first run does not update an existing PostgreSQL volume.

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

Python 3.14 and Node.js 24 run in separate images with committed dependency lockfiles. PostgreSQL 18 includes pgvector. Compose runs `db`, a one-shot `migrate` service, `api`, and `web`. See [architecture](docs/architecture.md), [ADRs](docs/adr/README.md), and [engineering conventions](AGENTS.md).

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

This uses an isolated Compose project on ports 18000/13000, validates both configurations, runs backend lint/format/tests and frontend lint/types, builds production images, checks HTTP responses and migrations, and verifies database persistence after container recreation. Its temporary database is removed on exit. Set `CHECK_API_PORT` and `CHECK_WEB_PORT` if those ports are occupied.

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

The first migration enables `vector`; there are no domain tables. Register future models with the declarative base so Alembic can discover their metadata.

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
