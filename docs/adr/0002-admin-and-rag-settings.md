# 0002: Single-owner administration and RAG configuration

Status: Accepted

The portfolio needs private configuration before its RAG pipeline exists. Keep ownership and storage within the existing FastAPI/PostgreSQL stack, without an external identity service or frontend persistence.

- Bootstrap one Argon2id-hashed account after migrations, using initial environment credentials only if no account exists. Database values remain authoritative.
- Store opaque session-token hashes in PostgreSQL. Cookies are HttpOnly, SameSite=Lax, and Secure for HTTPS origins. Require the configured origin on mutations, throttle login failures on the administrator row, and revoke all sessions when credentials change.
- Use a fixed-destination Next.js proxy for browser requests. Protect API endpoints independently; authenticated responses are never cached.
- Encrypt write-only provider keys with Fernet and a stable environment key. Loss of that key requires replacing provider credentials. Keep provider requests server-side and sanitize errors.
- Persist a validated configuration document for chat, OpenAI embeddings, optional LLM reranking, and future retrieval/chunking. Explicit connection tests exercise the chosen provider using saved or draft credentials, without persisting drafts.

This supports one administrator, with no registration, email recovery, or multi-user roles. It does not implement ingestion or public chat. Model suggestions are editable; the provider decides model availability during connection tests.
