# 0013: Parallel criterion research and direct semantic fallback

- Status: Accepted
- Date: 2026-10-30
- Supersedes: the database-first research gate in ADR 0010 and the fixed research operation budget in ADR 0007

## Context

The supervisor already gathered independent specialist calls concurrently, but the first turn hid RAG and rejected mixed database/RAG batches. Broad text research consequently waited for database research and another supervisor decision. Criteria were extracted only for role-fit questions. An empty database result also needed another supervisor turn to request text evidence.

## Decision

Extract explicit criteria for factual career questions as well as explicit and inferred role-fit criteria. Preserve Boolean conditions, dates, exclusions, pagination, and same-project requirements in the complete factual question; decomposing it does not authorize relaxing an exact query. Research tasks identify the criteria they investigate. Missing criterion coverage is reported to the Representative.

Expose both specialists from the first Analyzer turn and instruct it to batch all independent searches. Dispatch each batch with `asyncio.gather`. Broad RAG can run concurrently with database research or alone for a narrative question. A semantic search that depends on a returned result-set handle still waits for that result. Exact factual semantic evidence remains scoped when an exact database search has been requested, including when the RAG call appears first in a mixed batch. Role-fit semantic research may investigate current jobs, projects, and documents without relying on project skill tags. Empty or invented scopes never become broad searches.

Add opt-in `fallback_to_rag` to database tasks. When the database returns zero result rows, immediately dispatch related, unscoped text research for the delegated question and criteria. This runs within that database task while sibling research continues, without another Analyzer decision. The Analyzer authorizes fallback only when semantic evidence is useful and alternatives are allowed, and avoids it when equivalent broad RAG research is already planned. It stays off for counts-only requests. Preserve the original database evidence and exact zero even if fallback fails or the budget is exhausted. Failed database operations are unknown, not empty results, and do not trigger this fallback.

Keep four Analyzer decisions and the existing research/answer deadlines. Allow eight research operations or three per extracted criterion, whichever is larger, up to 24 for eight criteria. Initial specialist calls, repairs, and fallbacks share this budget. Keep the final Representative's text stream and optional verified components. Preserve customized prompts while upgrading unchanged shipped defaults.

## Consequences

Independent database and text searches can overlap, and database misses can reach semantic research without an extra supervisor round trip. Dependent scope queries and final synthesis still wait for their evidence. More criteria can use more concurrent provider calls within the same time limit; provider latency, rate limits, assessment, and optional component selection still affect response time.

Validate overlap with event barriers rather than timing-only assertions, including first-turn mixed batches, multiple database criteria, fallback while another database task remains active, operation limits, cancellation, and RAG-only composition. Preserve exact-count, scope, prompt-upgrade, and component tests, then run the full isolated application checks before deployment.

The required isolated check passed 313 backend tests and 44 browser tests, including lint, types, production builds, migration checks, and persistence checks. An instrumented real-model role-fit run launched four Database and three RAG specialists within 0.4 seconds in the first research batch. Single-run total timings remained approximately one minute, so these observations establish parallel execution rather than a consistent end-to-end speedup. After deployment, the public exact-filter smoke test returned four Python/PostgreSQL projects, matching the independent database count, with no RAG or alternative search. All services were healthy, and before/after snapshots confirmed unchanged career/embedding counts, saved configuration, and encrypted provider keys. A verified PostgreSQL backup and prior API image were retained; no migration was needed.
