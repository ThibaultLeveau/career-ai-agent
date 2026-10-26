# 0005: Skills as project metadata and current ingestion overview

Status: Accepted

## Decision

Jobs, projects, and documents are ingestion sources. Each job combines its structured fields into one source document; each project combines its fields, linked job title/company, and sorted skill keywords. Token chunking with overlap runs over the complete document before embedding. This retains the combined-document behavior described in ADR 0004.

Standalone skills are vocabulary, not separate retrieval documents. Skill changes still invalidate the projects using those keywords. Separate eligible ingestion types from historical types in the API and web application; historical filters retain skills, while enqueue, worker claims, status polling, and backfill exclude them.

Migration 0005 cancels unfinished skill jobs and removes their text/chunks/vectors, retaining skill records, project associations, source/history linkage, metadata, and logs. A downgrade cannot reconstruct these derived vectors; older code can re-ingest retained skill records. Stop old API/worker processes during migration to prevent new legacy jobs.

Admin overview totals represent existing items, each counted once using the same revision/settings checks as content status indicators. Pending includes queued, unindexed, outdated, cancelled, and superseded states; ongoing includes running/retrying; failed and successful represent the latest outcome, with success requiring current content/settings. Skills and deleted items do not contribute to ingestion totals. Batch latest-job queries keep dashboard and status polling independent of record count.

## Consequences

Skills remain useful for editing, filtering, and project context without producing isolated keyword vectors. Operational history is retained and labeled as legacy, so historical run counts differ from current ingestion totals. The UI uses compact status icons and accessible shared row menus; status polling does not replace editor state. The funnel depicts a current-state snapshot with failure/success branches, not a conversion-rate history.
