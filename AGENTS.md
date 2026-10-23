# Engineering conventions

- Keep changes scoped to the issue. Prefer small modules, typed interfaces, and direct code over speculative abstractions.
- Keep comments sparse and explain only non-obvious reasons. Link documentation instead of duplicating instructions.
- Backend routing belongs in `apps/api/app/api`, configuration in `core`, and SQLAlchemy wiring in `db.py`. Add domain modules only when a feature needs them.
- Use synchronous SQLAlchemy sessions with synchronous database handlers. Close sessions through the dependency and manage schema changes with Alembic, never `create_all()` or application startup.
- Use strict TypeScript and server components by default. Keep database credentials and other secrets out of frontend code.
- Change dependencies through uv/npm and commit the matching lockfile. Keep runtime versions aligned with Dockerfiles; rebuild development images after manifest/configuration changes.
- Record significant architectural decisions in `docs/adr`. Keep README setup instructions accurate.
- Run `sh scripts/check.sh` before handing off a change. See README for focused checks and container workflows. Report skipped checks and failures explicitly.
- Preserve existing user changes. Do not commit secrets or generated build output. Do not merge pull requests unless explicitly requested.
