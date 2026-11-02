# 0016: Compact chat workspace

Status: Accepted

## Context

Long answers, full-width tables, large resume cards, and the composer made individual responses span multiple screens. Recruiters need a concise answer alongside supporting work, with navigation and follow-up input readily available.

## Decision

Use a viewport-height desktop workspace from 1024px with independently scrolling conversation and results columns. Keep the shared public header fixed and reserve its height on every public page. The composer stays below the conversation. On smaller screens, retain a single document flow with widgets beneath their original answers and a sticky composer.

Keep streamed turns and blocks as the source of truth. UI-only selection follows the latest turn with project/job components, or pins a manually selected earlier turn until another question is submitted. Label retained results with their originating question. Text-only and resume-only turns do not clear previous results. Resume downloads, introductions, progress, sources, and failures remain in the conversation. Reset clears all selection; stop/error preserve already received verified widgets without changing completed-history rules.

Render one widget instance per visible block. Original turn IDs and block indices identify pagination updates. Successful list responses persist in the owning block; switching views aborts pending requests and restores the last confirmed state. Existing signed detail actions, scope, pagination, and SSE contracts remain unchanged.

Replace chat tables with compact records and two-line summaries. Show four skills initially and disclose the rest. Reduce resume and composer spacing without shrinking interaction targets. Preserve the site's themes, semantic controls, keyboard navigation, reduced-motion behavior, and expandable narratives.

Apply shared visitor-facing writing instructions across synthesis, clarification, and component introductions: at most 15 words per sentence and eight per complete bullet, including labels. There is no total word or bullet-count cap. Preserve factual names, material uncertainty, and requested completeness. Instructions apply after editable prompts; known shipped defaults upgrade through existing fingerprints while custom prompts remain intact. Keep streaming instead of buffering or mechanically truncating text.

## Consequences and validation

Long conversations and detailed results remain scrollable while desktop controls remain visible. Generated word limits are best-effort model behavior, requiring real English/French evaluation alongside deterministic prompt-delivery tests. No schema migration, dependency, or public API change is introduced.

Browser coverage checks laptop fit, mobile stacking, result selection, pagination persistence, independent scrolling, streaming, accessibility, and fixed navigation on browsing pages. The repository's full isolated validation and existing Compose deployment workflow remain required.
