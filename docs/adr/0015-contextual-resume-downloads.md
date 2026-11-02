# 0015: Document types and contextual resume downloads

- Status: Accepted
- Date: 2026-11-02
- Extends: [0003](0003-career-content.md), [0010](0010-verified-chat-components.md)

## Decision

Store document types in a catalog with permanent `resume` and `other` keys and add-only custom types. Migration 0007 classifies existing files as `other` and keeps every file unavailable for public download. Resume publication requires a per-document admin switch. Retyping a resume to another type disables publication. Optional matching notes identify intended audiences without becoming factual career evidence. Classification and publication metadata do not change document ingestion fingerprints.

Extend the shared career assessment with explicit resume requests and a concrete hiring opportunity's role and stated requirements. A direct request or a role plus an explicit requirement enables selection. Inferred requirements alone do not. Both chat modes select among currently enabled resumes using current PDF text, titles, and matching notes. Reuse revision-current extraction and the bounded PDF reader instead of depending on embeddings. Honor requested document language, prefer conversation language after relevance, and break equivalent matches by update time and ID. Ambiguous variants ask one targeted clarification; unresolved or failed selection omits the card without breaking the answer.

Emit a server-hydrated `resume_download` component after ordinary answer blocks, using the existing SSE component contract. The model selects only from eligible document identities; it never authors download URLs or file metadata. Add document references to history and browser-held offered IDs plus clarification state across bounded history truncation. These values are conversation hints, never authorization or factual evidence. A new conversation resets them. The `resume_state` event communicates clarification state separately from prose.

Purpose-specific Fernet references identify the document. Public download and component hydration check current type and availability again. The public API exposes no document catalog or arbitrary-file route. The same-origin web proxy forwards no administrator credentials. Files download as PDF attachments with safe filenames, `nosniff`, and `no-store`; key rotation, disabling, reclassification, and deletion revoke references. Existing admin downloads remain authenticated. This is the explicit exception to the private-download policy in ADR 0003.

## Consequences

Owners must classify and enable existing resumes after deployment. Available resumes are public files and their download references can be shared. Matching can read fresh uploads without successful embeddings and remains bounded by the chat deadline. The interface offers stored PDFs only, using fixed React rendering and the site's existing responsive themes. No generated resume, server conversation store, new provider, or new infrastructure is introduced.

The optional selector supports up to 40 enabled variants, a 20-second selection deadline, five seconds of fresh PDF extraction, and a shared 10,000-token document-text budget. Larger catalogs or exhausted limits omit the optional offer rather than choosing an unchecked file. A direct request with one enabled resume and no explicit document-language requirement needs no selection call.
