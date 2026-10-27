# 0006: Public career chat and retrieval

Status: Accepted

## Decision

Serve a narrow, public career conversation on the homepage. The assistant explicitly represents Thibault with AI, answers in first person using supplied career evidence, and follows the visitor's language. Store conversation state only in browser memory; send bounded completed history with each question. There is no public configuration or document-download endpoint.

Use the existing FastAPI, SQLAlchemy, PostgreSQL/pgvector, and HTTPX stack. Keep database operations synchronous and use asynchronous provider streaming so disconnects close the upstream response promptly. Read saved admin settings per request. Extend retrieval configuration with semantic/hybrid mode and a neighboring-chunk window, defaulting to hybrid and one chunk per side. Existing JSON configuration accepts these defaults without a schema migration or re-ingestion.

Search only the active, successfully published generation of extant jobs, projects, and documents, filtered by embedding provider/model/dimensions before vector comparison. Keep previous compatible generations usable while replacement ingestion is pending or fails. Use exact cosine ranking for the small career corpus. In hybrid mode, combine semantic and PostgreSQL full-text rank lists with equal-weight reciprocal rank fusion, retaining the configured number of candidates. No approximate vector index or separate search service is needed.

Materialize ranked candidates and neighboring text within one short consistent database snapshot. A concurrent ingestion publish may remove old chunks, so do not defer neighborhood loading until after a provider call. Release database transactions before query embedding, reranking, or answer generation. When enabled, rerank through the configured generation provider, validate returned candidate IDs, and retain the retrieval order on failure. Select the configured context count, expand within the same generation, merge overlapping windows, and remove duplicate text within bounded context.

Use a fixed-destination public Next.js proxy separate from administration. Normalize OpenAI and Anthropic streams into SSE `delta`, `done`, and `error` events; successful completion includes source title/type and optional page ranges. Exactly one terminal event distinguishes completed replies from truncated connections. Stream without caching or buffering, forward cancellation, and bound requests and provider timeouts. Never forward provider errors, credentials, reasoning events, or private admin URLs to recruiters.

## Consequences

Retrieval changes apply to the next question without rebuilding embeddings. Embedding-model changes require compatible re-ingestion; unavailable content produces an explicit helpful response instead of an invented biography. Reranker failures reduce ranking quality but do not unnecessarily prevent answering. Source labels identify the supplied context rather than granting access to the underlying private files. Conversation history supplies conversational context, never independent evidence for career facts.

The initial implementation uses exact database search suited to the existing corpus. Larger corpora can justify indexes and additional retrieval evaluation later. Provider calls are billable; tests mock providers, while deployment verification uses a small real request. Existing deployment backups include career data, embeddings, encrypted keys, and saved settings; retain the encryption environment alongside database backups.

References: [pgvector hybrid search](https://github.com/pgvector/pgvector#hybrid-search), [OpenAI streaming](https://developers.openai.com/api/docs/guides/streaming-responses), [Anthropic streaming](https://platform.claude.com/docs/en/build-with-claude/streaming).
