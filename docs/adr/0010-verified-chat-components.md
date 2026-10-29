# 0010: Database-first answers and verified chat components

- Status: Accepted
- Date: 2026-10-28
- Extends: [0007](0007-agentic-career-research.md), [0008](0008-composable-career-queries.md)

## Decision

In Agents mode, require a database research attempt before RAG or factual composition. Reject premature semantic calls, including in mixed first batches. Clarification, greetings and redirects can bypass research. A failed search remains unknown; a run that cannot begin database research may only explain the limitation or clarify. Preserve criterion-level role-fit research and strict exact-versus-related scopes.

The Representative selects up to four typed presentation references and generates an introduction for each before streaming its prose. Allow one selection repair within the existing total deadline. The backend hydrates Project List, Job List, Project Card and Job Card from current records. Unknown references, blank introductions, mismatched types and invalid job/project ordering are rejected. The Representative capability test now checks native tool calling, as do the other roles. Existing provider adapters serve both OpenAI and Anthropic; no orchestration dependency is added.

Keep primary result membership separate from supporting source lineage. Basic record queries retain complete ordered membership. Composable queries expose primary IDs only when individual root records are represented, including groups keyed by root ID; arbitrary aggregate groups cannot become record lists. Deduplicate join-expanded membership without changing requested ordering. Aggregate rankings keep their Markdown rendering.

Extend SSE with `component` events containing an AI introduction and a discriminated component payload. The browser retains ordered text/component blocks. Existing status, text, source-footer and terminal semantics remain. No model-authored HTML or record fields are used to build these views. Stored descriptions use the existing restricted Markdown renderer.

List tokens use the existing Fernet configuration key to authenticate and encrypt entity type, ordered matched IDs and page size. They are stateless and purpose-separated from detail tokens. Membership is a snapshot of the original verified result, limited to 10,000 records. Subsequent pages read current content, remove deleted records from totals, and clamp out-of-range pages; new matches require a fresh question. Key rotation invalidates old navigation tokens. The same-origin `/api/chat/components/page` proxy forwards to `/chat/components/page`, with bounded bodies, cancellation, origin checks and no caching. Pagination and the single literal text filter never call a model and never expand the original scope.

Detail buttons submit a readable follow-up and an authenticated record action. Reload the selected record by identity and use the Representative to introduce its card, without replanning the target. A job card must be followed by a separately introduced list of all associated projects when any exist, irrespective of preceding filters. Associated lists cannot be presented independently as filtered matches. Compact displayed-record references in completed history provide navigation context only, never factual evidence. Conversation state remains in browser memory.

Add defaulted `chat_components` JSON configuration with independently validated project/job page sizes, default 5 and range 1–20. Settings apply when a list is created, including job-associated project lists. Older settings load defaults; no schema migration or re-ingestion is required. Keep the RAG-only fallback unchanged and preserve customized agent prompts when upgrading shipped defaults.

## Consequences

Presentation selection adds one model call, with at most one repair. List navigation is independent of model latency and does not consume research budgets. Public views use fixed React renderers and the existing themes. Automated validation covers verified membership, literal filtering, detail identity, settings isolation, SSE validation, cancellation/retry, and mobile/keyboard interaction. Live evaluation must inspect components as well as prose; the evaluator records component data without navigation tokens.
