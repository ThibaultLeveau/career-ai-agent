# 0009: Career boundary and criterion-based role fit

Status: Accepted

## Context

A general career instruction allowed unrelated tasks, while exact skill filtering could omit transferable backend experience when assessing a PHP role. Public dark colors also differed from administration.

## Decision

Run a shared, validated request assessment before research in both chat modes. Use the existing Analyzer model for agentic assessment and the chat model for RAG-only assessment. The internal result distinguishes factual career requests, role-fit requests with explicit/inferred criteria, and brief redirects. A failed assessment terminates with a sanitized error. Redirects do not read the career catalog, retrieve evidence, or invoke final synthesis. Mandatory career rules remain independent of customized prompts.

Role-fit research carries validated criterion references into specialists and evidence. Direct and transferable branches remain distinguishable; factual exact intersections retain their existing constraints. The Representative receives criteria, evidence and limitations, and distinguishes development from migration/hosting. RAG-only fit uses at most three focused searches with interleaved deduplication and the existing context limit. Agentic assessment is included in the existing research and total deadline budgets.

Track all recognized historical shipped prompt hashes when upgrading defaults, preserving customized prompts. Public APIs, SSE frames, saved agent roles and database schema remain unchanged. The shared global dark palette uses administration's existing colors; light palettes remain distinct.

## Consequences

Assessment adds a model request. Classification and semantic relevance remain model decisions, so behavior requires live evaluation as well as mocked integration tests. No corpus rewrite, re-ingestion or schema migration is needed. Missing or failed evidence must remain uncertainty, not a claim that experience does not exist.
