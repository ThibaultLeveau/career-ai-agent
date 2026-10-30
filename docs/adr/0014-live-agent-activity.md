# 0014: Live agent activity

- Status: Accepted
- Date: 2026-10-30

## Context

A single status string replaces one agent's progress with another's during parallel research. Row totals describe database implementation details rather than the work visitors care about, and messages emitted only after specialist model calls leave the beginning of each search unexplained.

## Decision

Extend each existing SSE `status` event with an `activities` snapshot. Retain `stage` and `message` for older clients. Each activity has a stable `id`, public `agent` label, short `message`, and `state` (`running`, `complete`, or `error`). The browser replaces its snapshot rather than accumulating a history of events. It accepts the previous status format and validates snapshot sizes, IDs, strings, and states.

Track actual dispatch lifecycles on the server. Start activity before awaiting a specialist; finish it on success, failure, or cancellation. Complete the database activity before its optional RAG fallback starts. Group simultaneous database tasks by combined factual criteria, independent role-fit/related criteria, or general record research. Count distinct supplied criterion IDs across each active group and display their assessment labels in stable criterion order. Each criterion has a required, specific display label of at most 40 characters alongside the full research requirement. A label such as “Python + Docker backend” keeps meaningful terms visible even when the requirement starts with “List projects where…”. Normalize whitespace and cap labels at 40 UTF-16 units so all eight fit within the browser's status limit. Labels are produced in the existing assessment call, preserving the full requirement for research; no extra model call is needed. Names and counts shrink together as tasks finish. Group RAG tasks into broad and scoped text searches, counting actual delegated tasks. Do not display query rows, raw arguments, private reasoning, or simulated progress.

Show Query Analyzer Agent while assessing, planning, and reviewing results. Show database and RAG groups together when their research overlaps. Retain a completed group while sibling work continues, then replace the snapshot when the Analyzer reviews results or the Answer Agent prepares the reply. During streamed text, show Answer Agent writing the answer. Clear activity on completion, failure, stop, and reset.

Render compact stacked lines beneath the assistant identity with staggered dots for running work, checks for completion, and a subdued unavailable indicator. Keep the existing light/dark palette, use short entry transitions, and disable motion for reduced-motion preferences. On narrow screens, place each description below its agent label. Announce current running work politely without repeatedly announcing completed work. Activity never enters conversation history.

## Consequences

Visitors can see parallel work without confusing it with a serial log or an invented progress bar. No additional model request, dependency, database migration, or saved setting is needed. Test overlapping task lifecycles and cleanup, snapshot validation, text streaming, history isolation, mobile layouts, and reduced motion; verify the full application before deployment.
