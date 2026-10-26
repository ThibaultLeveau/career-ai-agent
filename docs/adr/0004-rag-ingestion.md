# 0004: Durable RAG ingestion in PostgreSQL

Status: Accepted

## Decision

Use a dedicated Python worker and a PostgreSQL queue alongside the existing synchronous API. Saving a source and requesting ingestion share one transaction. This avoids another broker and survives application restarts. One worker runs by default; `SKIP LOCKED` claims and a partial unique index support concurrent workers and prevent duplicate active jobs per source.

Keep source revision/hash, job settings snapshots, operational events, extracted text, and per-chunk progress. A 120-second lease renewed every 10 seconds fences abandoned workers. Persist retry schedules and batch completion; use three extra retries by default for transient failures, with jitter and `Retry-After`. Provider calls run outside database transactions. Workers re-read encrypted keys on each attempt.

Content saves coalesce while a job is active. Revision checks prevent publishing obsolete results and enqueue the latest content afterward. Project text includes linked job title/company and skill keywords, so relevant relationship changes invalidate projects. Settings fingerprints include only embedding and chunking choices; changes mark completed data out of date and require explicit re-ingestion.

Use pypdf in a resource-limited subprocess, tiktoken for Unicode-safe token windows, and pgvector's variable-dimension vector type with model/dimension metadata in the job. No approximate vector index is needed before retrieval exists. Only a fully successful generation becomes active. Remove superseded vectors after successful replacement; failed replacements retain the previous generation. Deletion removes extracted text/vectors and cancels active work, retaining job metadata and logs.

## Consequences

Ingestion is at least once: a crash after a provider response but before its database checkpoint can repeat that request. Published results remain idempotent. UI polling uses independent state so editing forms are preserved. No OCR, public retrieval, or chat is introduced. Logs are private, sanitized, and retained without automatic pruning. Database backups include all ingestion state.
