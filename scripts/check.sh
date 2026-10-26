#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

export COMPOSE_PROJECT_NAME="career-ai-check-$$"
export POSTGRES_DB=career_ai_check POSTGRES_USER=career_ai_check POSTGRES_PASSWORD=check-only
export ADMIN_INITIAL_USERNAME=check-admin ADMIN_INITIAL_PASSWORD=check-only-long-password
export SETTINGS_ENCRYPTION_KEY=eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg=
export APP_ORIGIN=http://web:3000
export API_PORT="${CHECK_API_PORT:-18000}" WEB_PORT="${CHECK_WEB_PORT:-13000}"

compose() {
    docker compose --env-file .env.example "$@"
}

dev() {
    compose -f compose.yaml -f compose.dev.yaml "$@"
}

cleanup() {
    status=$?
    trap - EXIT
    if [ "$status" -ne 0 ]; then
        compose logs --no-color || true
    fi
    compose down --volumes --remove-orphans || true
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

compose config --quiet
dev config --quiet
dev build api web
dev run --rm --no-deps api uv lock --check
dev run --rm --no-deps api ruff check .
dev run --rm --no-deps api ruff format --check .
compose up --wait db
dev run --rm migrate
dev run --rm --no-deps -e TEST_ADMIN_DB=1 api pytest
dev run --rm --no-deps web npm run lint
dev run --rm --no-deps web npm run typecheck

compose up --build --wait --wait-timeout 120
curl --fail --silent --show-error "http://127.0.0.1:$API_PORT/health"
curl --fail --silent --show-error --output /dev/null "http://127.0.0.1:$WEB_PORT"
compose -f compose.yaml -f compose.test.yaml build e2e
mkdir -p apps/web/test-results
compose -f compose.yaml -f compose.test.yaml run --rm --no-deps --user "$(id -u):$(id -g)" e2e
compose run --rm --no-deps migrate alembic check
compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "UPDATE rag_configuration SET configuration = jsonb_set(configuration::jsonb, '{ingestion,chunk_size}', '950');"
compose stop worker
compose run --rm --no-deps migrate alembic downgrade 0003
test "$(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT configuration->'retrieval'->>'chunk_size' FROM rag_configuration")" = "950"
compose run --rm --no-deps migrate alembic upgrade head
test "$(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT configuration->'ingestion'->>'chunk_size' FROM rag_configuration")" = "950"
compose run --rm --no-deps migrate alembic downgrade base
compose run --rm --no-deps migrate alembic upgrade head
compose run --rm --no-deps migrate alembic upgrade head
compose run --rm migrate

verify_database() {
    test "$(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM pg_extension WHERE extname = 'vector'")" = "1"
    test "$(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT version_num FROM alembic_version")" = "0004"
}

verify_database
compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "CREATE TABLE initialization_probe (id integer PRIMARY KEY); INSERT INTO initialization_probe VALUES (42);"
compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "UPDATE administrator SET username = 'persisted-admin'; UPDATE rag_configuration SET configuration = jsonb_set(configuration::jsonb, '{ingestion,chunk_size}', '900');"
compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
INSERT INTO job (id, title, company, location, ongoing, summary, responsibilities, achievements)
VALUES (100, 'persisted-job', 'Acme', '', false, '', '', '');
INSERT INTO skill (id, keyword) VALUES (100, 'persisted-skill');
INSERT INTO project (id, name, role, ongoing, summary, description, outcomes, website_url, repository_url, job_id)
VALUES (100, 'persisted-project', '', false, '', '', '', '', '', 100);
INSERT INTO project_skill (project_id, skill_id) VALUES (100, 100);
INSERT INTO document (title, filename, size, content)
VALUES ('persisted-resume', 'resume.pdf', 8, decode('255044462d312e37', 'hex'));
SQL
compose down
compose up --wait --wait-timeout 120
verify_database
test "$(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT id FROM initialization_probe")" = "42"
test "$(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT username FROM administrator")" = "persisted-admin"
test "$(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT configuration->'ingestion'->>'chunk_size' FROM rag_configuration")" = "900"
test "$(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT count(*) FROM project p JOIN job j ON p.job_id = j.id JOIN project_skill ps ON ps.project_id = p.id JOIN skill s ON s.id = ps.skill_id WHERE p.name = 'persisted-project' AND j.title = 'persisted-job' AND s.keyword = 'persisted-skill'")" = "1"
test "$(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT encode(content, 'hex') FROM document WHERE title = 'persisted-resume'")" = "255044462d312e37"
compose stop db
test "$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
    "http://127.0.0.1:$API_PORT/health")" = "503"
compose up --wait --wait-timeout 120 db
curl --fail --silent --show-error "http://127.0.0.1:$API_PORT/health"
printf '\nAll checks passed.\n'
