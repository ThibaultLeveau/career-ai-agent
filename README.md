# Career AI

An AI-powered personal portfolio with public experience browsing, a career chatbot, and authenticated administration. Recruiters can explore jobs and projects directly or ask about Thibault's experience and skills in a centered conversation with streamed answers and compact source labels. Optional agentic mode combines exact database queries with semantic evidence before composing an answer. The admin panel manages career content, encrypted OpenAI/Anthropic keys, retrieval settings, and agent prompts and models. A durable background worker extracts text, chunks content, and stores embeddings for semantic or hybrid retrieval.

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

In **Settings → AI Provider**, save provider keys separately from model settings. OpenAI supports embeddings; both providers support chat and LLM-based reranking. Reranking starts disabled. Models can be selected from suggestions or entered by API ID; availability is checked with **Test**. Tests use current form values, make a small billable request, and never save changes. No provider request is made on Save. Use **Settings → RAG** for search mode, retrieval counts, neighboring-chunk expansion, and ingestion chunk size, overlap, and retry count.

Use **Settings → Agents** to enable agentic mode, edit each agent's prompt, or choose a separate provider/model. Existing saved configurations default to agentic mode disabled; enabling it is an explicit settings change after validation. Turning it off restores the existing RAG-only chat on the next question.

The example credentials are for local development. Set database credentials and host ports in `.env`; this file is ignored by Git. Web/API ports bind to localhost; PostgreSQL is reachable only inside Compose. Changing database credentials after the first run does not update an existing PostgreSQL volume.

## Public experiences

The shared public header links **Home** and **Experiences → Jobs / Projects**. Browse [Jobs](http://localhost:3000/jobs) as a chronological list and [Projects](http://localhost:3000/projects) as a responsive card grid. Both collections show 12 records per page, ordered by start month newest first, undated records last, then descending ID. Search covers the complete collection, including narrative fields and related metadata. Jobs filter by company, skill, and status; projects filter by professional/personal type, linked experience, skill, and status. Skills shown for a job come from its linked projects. **Past** means the record is not marked ongoing, including undated records.

Filters combine and remain in the URL (`q`, `company`, `skill_id`, `status`, `kind`, `job_id`, and `page`, as applicable). Changing a filter returns to page one; dropdown choices come from the complete collection. Detail pages at `/jobs/[id]` and `/projects/[id]` retain the originating list filters in their back link, support direct links and reloads, and connect jobs with their projects. Populated narrative sections render safe Markdown, while missing sections are omitted. Deleted or unknown records return 404. All public pages share the existing light/dark theme choice, support keyboard navigation, and respect reduced-motion preferences.

Browsing reads current structured content without chat, model calls, embeddings, or ingestion prerequisites. Admin edits become available on subsequent page loads. Anonymous read-only API routes are `GET /public/jobs`, `GET /public/jobs/{id}`, `GET /public/projects`, and `GET /public/projects/{id}`. List routes return records, total and matching counts, pagination, and filter choices. Their explicit public response types omit ingestion state, timestamps, administrative data, and chat tokens. The web server calls these endpoints with uncached reads and bounded timeouts; it does not forward administrator cookies. There is no separate publishing workflow or migration for this feature. See [ADR 0012](docs/adr/0012-public-experience-browsing.md).

## Public career chat

The public site and administration share theme selection and the same charcoal-and-lavender dark palette; their existing light palettes remain distinct. They follow the device preference initially; the sun/moon control remembers a manual choice across pages, reloads, and tabs. Theme changes preserve active conversations and unsaved forms. If browser storage is unavailable, switching still works for the current page session.

The homepage identifies the chatbot as an AI representation of Thibault. It answers in first person and follows the visitor's language while the interface remains English. Suggested questions help recruiters start; follow-up questions use recent completed conversation turns and freshly retrieved evidence. Conversations remain in browser memory and reset on reload or **New conversation**. Interrupted replies are not sent back as completed history.

Both chat modes assess each request before research. Unrelated questions, tutorials, coding/debugging tasks, greetings, and thanks receive a brief career-focused reply without retrieval or sources. Mixed requests are answered only for their career-related portion. Follow-ups use recent completed history. Assessment failures end with a sanitized error rather than allowing unrestricted generation.

Job-fit questions are decomposed into explicit requirements and inferred responsibilities. Research collects direct experience and transferable capabilities independently; for example, PHP development suitability can draw on documented Python backend development alongside PHP migration work without equating migration with PHP feature development. Exact factual filters and skill intersections keep their strict meaning. RAG-only fit assessments run at most three focused searches and interleave/deduplicate their results within the existing context budget. Assessment adds one bounded model call using Query Analyzer in agentic mode or the chat model in RAG-only mode; no additional model setting is required.

The browser posts to a same-origin `/api/chat` proxy, which streams the API's `/chat` response without forwarding admin cookies. SSE `delta` events carry text; `component` events carry typed views with generated introductions; `done` carries source labels; `error` ends an interrupted response with a sanitized message. Agentic mode also emits `status` events for brief activity messages while researching and preparing an answer. These describe actual actions and outcomes without exposing private reasoning, prompts, or SQL. An unexpected end of stream is treated as interruption. Stop/reset cancels the request. Requests, conversation history, provider calls, reranking inputs, and expanded context are bounded. No provider credentials or retrieval controls reach the browser. Answers support paragraphs, lists, and Markdown tables; raw HTML and embedded images are not rendered. Source attribution appears only in the Sources section after each answer, without repeated source sentences in the prose, tables, or lists.

Retrieval uses only published job, project, and document chunks compatible with the configured embedding model and dimensions. **Semantic** search uses cosine similarity; **Hybrid** (the default) combines semantic and PostgreSQL full-text ranks. Optional reranking uses the saved AI settings and falls back to retrieval order on failure. **Window size** adds that many adjacent chunks on each side of a selected match (default 1; 0 disables expansion), with overlapping windows deduplicated. Source labels identify the supplied context and optional PDF page ranges; they do not expose private document downloads or admin links.

Choose a chat model and save the required provider keys before using chat. RAG-only chat requires at least one successful ingestion with compatible embeddings; empty or incompatible corpora produce a helpful unavailable response. In that mode, a failed replacement ingestion leaves the previous published generation available. Agentic semantic searches use current published revisions so older excerpts cannot contradict newly edited structured records. Changing embedding model/dimensions requires re-ingestion before those sources can be searched with the new configuration. Retrieval-only changes take effect on subsequent questions and do not require re-ingestion.

## Agentic mode

Live activity appears beneath the assistant identity as named agent lines. Database checks show the number and names of distinct criteria being investigated together or independently, such as “Checking 2 criteria together (Python, backend)…”. Long criterion descriptions are shortened for readability. RAG shows the number of broad or scoped text searches. Concurrent work remains visible on separate lines, completed work receives a check, and each new planning or answer phase replaces the previous snapshot. Gentle motion respects reduced-motion preferences. Counts and names reflect active research tasks, never row totals or simulated timers. See [ADR 0014](docs/adr/0014-live-agent-activity.md) for the stream contract.

The **Query Analyzer** extracts the visitor's criteria, including role, skills, responsibilities, actions, and constraints, then batches independent database and RAG research together. Those calls run concurrently from the first research turn. The **Database** agent translates natural-language requests into validated, read-only filters and exact counts. When the Analyzer enables `fallback_to_rag`, an empty database result immediately triggers related text research without another Analyzer turn. The **RAG** agent retrieves narrative evidence; broad research can run alongside database calls or alone for narrative questions. Searches restricted to a database result set wait for that result and cover its complete matching set. Once enough evidence is available, **Thibault Representative** streams a text answer in the visitor's language and may add verified project/job list or card components. Aggregate rankings remain Markdown tables. Clarification and redirects can bypass research.

Each role in **Settings → Agents** has an editable prompt and a reset-to-default button. By default its provider, model, and maximum output tokens inherit **AI Provider → Chat**. Select **Use a different model** to override all three for that role; provider keys remain managed in AI Provider. Each **Test** button uses the draft settings and saved key without saving changes. All four agent tests check native tool calling, including the Representative’s presentation selection. Both OpenAI and Anthropic are supported. Explicitly supported GPT-6-family model IDs use low reasoning effort for agent tool decisions and final synthesis; other models and RAG-only generation retain their default reasoning settings. Editable prompts guide behavior; they do not grant new tools, allow writes, or replace the application's argument validation and evidence rules.

Database matching uses the stored project skills. Multiple required skills must occur on the same project; matching jobs are counted once through a qualifying project. Terms are case-insensitive literal matches, with boundaries for short terms: `AI` matches `Agentic AI`, while `OpenAI`, `LLMs`, and `RAG` are not automatic exact matches for it. The Analyzer may investigate useful related concepts separately. An empty AI-and-PHP intersection remains an empty exact result even if separate AI or PHP searches find projects. Counts describe recorded metadata, not every experience that may exist outside the stored content.

Project and job lists show five records per page by default, ordered by start month newest first with a stable ID tie-breaker unless another ordering was requested. **Settings → Chat components** controls their page sizes independently (1–20). The agent can select an ordered subset of verified records that matches its answer. Lists show a filtered count and **Show all** when narrowed; text search and pagination operate inside that selection without another AI call. **Show all** clears the filters and creates a fresh snapshot of the complete project/job catalog. Lists accompanying a job card remain within that job and are labeled **Projects from this experience**. Authenticated opaque tokens preserve scope and page size; pages read current fields and omit deleted records. Older tokens retain their original scope. Dates appear beneath titles, and list summaries display at most four lines. Clicking **✳ know more ...** sends a new chat turn with the selected record’s authenticated identity. The Representative introduces its card; job cards also show all associated projects when present. Completed history retains compact displayed-record references for contextual follow-ups, never as factual evidence. There is no server conversation store. See [ADR 0010](docs/adr/0010-verified-chat-components.md) and [ADR 0011](docs/adr/0011-markdown-and-compact-career-components.md).

Current structured records can support counts and answers before ingestion succeeds or when embeddings are unavailable. Narrative retrieval still requires an embedding key and compatible current chunks. Missing or failed research is reported as a limitation, not a zero count. Runs allow up to four Analyzer decisions and a shared research budget of eight operations or three per extracted criterion, whichever is larger (at most 24). Initial searches, fallbacks, and specialist repairs all consume that budget. The 120-second deadline remains: research gets at most 90 seconds, reserving at least 30 seconds for the Representative; the answer can also use unused research time. If research cannot finish, the Representative uses verified evidence already collected; an interrupted answer ends with an error. Agentic mode can make more billable model requests than RAG-only chat. Prompt, model, and mode changes apply to the next question and require neither migration nor re-ingestion. See [ADR 0013](docs/adr/0013-parallel-criterion-research.md).

## Career content

Use **Jobs**, **Projects**, **Skills**, and **Documents** in the admin sidebar to create, edit, search, and delete career content. Jobs and projects support month/year dates and Markdown narrative fields with **Visual** and **Markdown** editing modes. Overview retains the existing `summary` field; projects additionally have **My contribution**. Names, roles, employers, locations, and URLs remain ordinary inputs. Narrative sections allow 8,000 characters, with validation instead of truncation. Detail cards render safe Markdown; Overview starts expanded and other populated narrative sections are independently collapsible. Skills, context, and project links remain visible. A project linked to a job is professional; otherwise it is personal. Projects can reference multiple skills. Jobs with linked projects cannot be deleted until those projects are reassigned, unlinked, or deleted. Deleting a skill removes its associations and keeps the projects.

**Small Summary** is an editable, 280-character plain-text field reserved for lists. Its **AI Generation** button uses the current unsaved Overview and the configured **AI Provider → Chat** provider/model; it is disabled for an empty Overview. Generation produces a draft, and the normal Save action persists it. Provider/configuration failures preserve existing form content. Small Summary changes do not trigger embeddings. Project contributions participate in current-record search and ingestion.

After migration, fill missing Small Summaries using the same generator:

```sh
docker compose exec -T api python -m app.content.summaries backfill
```

The command skips populated summaries and empty Overviews, preserves concurrent edits, and reports failures; it can be rerun. AI calls never run inside the schema migration.

Documents accept multiple independent resume PDFs, up to 10 MiB each. Rename, replace, download, or delete them in the private admin workspace. File bytes are stored in PostgreSQL and included in its backups; replacement is atomic. Only authenticated administrators can download files. Saving new or changed jobs, projects, or documents atomically queues background ingestion; provider calls happen in the worker. PDFs require selectable text; OCR and encrypted PDFs are not supported.

Existing installations must run the migration service (`docker compose run --rm migrate`) using the rebuilt API image before starting the updated application. Migration 0004 adds ingestion storage and moves existing chunking values into ingestion settings without changing provider keys or models. Migration 0005 retires standalone skill ingestion: it cancels unfinished skill jobs and removes their derived text/vectors while preserving skills, relationships, history, and logs. Migration 0006 adds project contributions and Small Summary fields with empty defaults, preserving existing narratives. Stop the API and worker during migrations, then start the rebuilt services. Back up an existing database before migrating.

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

### Comparing real-model answers

The API runtime image includes `scripts/evaluate_agents.py` and the cases in `tests/fixtures/agent_evaluation.json`. List cases without database or provider calls, then compare selected cases using the saved models and keys:

```sh
docker compose exec -T api python scripts/evaluate_agents.py --list
docker compose exec -T api python scripts/evaluate_agents.py --mode both --case python_all,ai_php_intersection > /tmp/career-ai-agent-evaluation.jsonl
```

Evaluation enforces read-only database transactions and changes the mode only in memory; saved settings and career records are untouched. Runs other than `--list` make billable provider requests. Use `--mode agentic` or `--mode rag` for one pipeline, omit `--case` for every fixture, or repeat `--case` to select more cases.

Each JSONL result includes the answer, latency, activity, sources, database results, and comparisons with structured database oracles. Oracle checks compare exact counts, complete membership, and displayed pages; a nonzero exit indicates a run error or a failed required check. They do not validate narrative accuracy, language, grounding, or presentation: review the answer and each case's `review_expectations`, and inspect the actual filters, especially when both results are empty. RAG-only runs have no exact database evidence to compare. `model_usage` covers agent tool decisions only; it excludes streamed final answers, embeddings, reranking, and the RAG baseline, so it is not a complete cost report.

See the [issue 9 release evaluation](docs/agent-evaluation.md) for the initial paired comparison and its limits.

## Database and migrations

The first migration enables `vector`; the second adds the administrator, revocable sessions, encrypted provider credentials, and RAG settings; the third adds career content and PDF storage; the fourth adds ingestion jobs, logs, text, chunks, and vectors; the fifth retires standalone skill embeddings; the sixth adds project contributions and Small Summary fields. Login throttling lives on the singleton administrator record. Alembic imports the domain models so it can discover their metadata.

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

`down` preserves the named PostgreSQL volume. To permanently discard a disposable development database and start over:

```sh
docker compose down --volumes
docker compose up --build
```

If startup fails, inspect `docker compose logs db migrate api web`. A failed migration prevents API startup. A failed database probe makes `/health` return 503 with no connection details. If ports are occupied, change `API_PORT`/`WEB_PORT` in `.env`.

The deployed application at [thibault-leveau.com](https://thibault-leveau.com) also runs this repository's Docker Compose stack. Public HTTPS is supplied outside this Compose file; preserve the host's existing deployment configuration. Back up PostgreSQL and retain `SETTINGS_ENCRYPTION_KEY` before production updates, preserve the named database volume, run required migrations with the rebuilt API image, and verify application and health endpoints afterward. The agentic feature adds no schema migration. Enable it in Agents settings after validation; disable the same switch to return to RAG-only behavior.

The Database Agent supports composable read-only queries across skills, projects, jobs and document metadata, including relationships, grouped counts, rankings and overlapping timeline coverage. It can read current document text without embeddings. No migration or re-ingestion is needed for these capabilities. Shipped prompt defaults update automatically when unchanged; customized prompts and agent model overrides are preserved. See [query capabilities](docs/career-query-capabilities.md) for syntax, bounds and the real-model analytical evaluator. The existing Agents switch remains the immediate rollback to RAG-only.
