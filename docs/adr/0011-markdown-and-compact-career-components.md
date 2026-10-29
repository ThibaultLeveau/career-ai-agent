# 0011: Markdown content and compact career components

- Status: Accepted
- Date: 2026-10-29
- Extends: [0003](0003-career-content.md), [0010](0010-verified-chat-components.md)

## Decision

Keep PostgreSQL as the content source of truth. Store Markdown strings in existing narrative fields, retaining `summary` as Overview, and add project `contribution`. Use a client-only MDXEditor visual editor alongside an explicit raw Markdown mode; preserve the raw source until the administrator edits it. Preserve significant whitespace through validation and rendering, and reject oversized narratives without truncating them. Public views reuse the restricted Markdown renderer, with HTML and unsafe links disabled.

Add `small_summary` to projects and jobs as a separate plain-text field capped at 280 characters. An authenticated admin endpoint generates a draft from the unsaved Overview using the configured Chat provider/model. Save persists the result. A rerunnable command fills existing empty summaries outside migrations and protects concurrent edits. Summary-only edits do not change embedding input. Lists use Small Summary exclusively and clamp it to four lines; cards use Overview and independently collapsible narratives. Project contributions enter current-record queries and ingestion.

Allow the Representative to choose ordered IDs from a verified list target; validate membership and preserve exact/related evidence boundaries. Hydrate every displayed field from the database and provide selected identities to final answer generation. Keep list text filtering and pagination within the signed snapshot.

Supersede ADR 0010's prohibition on expanding a list only for explicit **Show all** navigation. New signed scopes permit expansion to the full entity catalog or, for a job-associated list, that job's projects. Expansion clears text search, resets to page one, and returns a fresh token. Never trust client-supplied IDs or scope boundaries. Legacy tokens do not grant expansion. Display filtered and catalog counts and label job-associated lists. Navigation requires no model calls.

## Consequences

An additive migration preserves existing content. MDXEditor adds an admin-only client dependency; public rendering remains lightweight. Rich editing can normalize Markdown spelling while preserving supported formatting; raw mode retains unsupported source for recovery. The separate summary backfill uses provider calls and reports individual failures. Automated checks cover persistence, generation failures, scope validation/expansion, editor recovery, responsive tables, and accessible disclosure controls.
