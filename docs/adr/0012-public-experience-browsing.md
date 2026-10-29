# 0012: Public experience browsing

- Status: Accepted
- Date: 2026-10-29
- Extends: [0003](0003-career-content.md), [0010](0010-verified-chat-components.md), [0011](0011-markdown-and-compact-career-components.md)

## Decision

Expose the existing job and project catalog through anonymous, read-only `/public/jobs` and `/public/projects` list and detail routes. Define dedicated public response types that exclude ingestion state, timestamps, administrative metadata, and chat tokens. Read current PostgreSQL records directly; browsing requires neither model calls nor successful ingestion. Job skills are the union of skills on linked projects, and project type continues to derive from whether a job is linked. No new publication state or schema migration is introduced.

Search and combined filters execute in the database across the complete collection. Lists contain 12 items per page, ordered by descending start month with undated entries last and descending ID as the tie-breaker. Filter choices describe the complete collection independently of current filters and pagination. Status uses the stored ongoing flag.

Render lists and dedicated detail pages with Next.js server components and a server-only API helper using uncached, time-limited requests. Keep navigation, theme controls, and URL-backed filters in small client components. Share the public header with chat and reuse the restricted Markdown renderer. Public links preserve list filters for return navigation; detail pages link related records and omit empty narrative sections. Unknown and deleted records return 404. Network failures use the public unavailable state without exposing backend internals.

## Consequences

Visitors can browse the portfolio without generating AI costs or starting a conversation, and administrative content updates are reflected on subsequent loads. All stored job and project content is publicly readable; private documents, settings, provider keys, ingestion details, and administrative operations retain their existing protections. The API and pages are covered by anonymous-access, public-field, filtering, pagination, relationship, freshness, safe-Markdown, theme, keyboard, and responsive-layout checks. Existing chat and administration contracts remain unchanged.
