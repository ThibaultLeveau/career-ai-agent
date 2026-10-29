# 0008: Composable, read-only career queries

- Status: Accepted
- Date: 2026-10-27
- Extends: [0007](0007-agentic-career-research.md)

## Context

Exact project/job filters cannot answer analytical questions such as listing every skill by its number of projects. Searching once per skill exhausts the supervisor budget, while semantic retrieval cannot establish complete counts or relationships.

## Decision

Extend the existing `query_database` tool with `query` and `read` operations, retaining `records` for compatibility. The Database specialist receives a server-owned catalog of skills, projects, jobs and document metadata. A typed expression tree describes selections, relationship joins, correlated existence filters, grouping, aggregate filters, ordering and pagination. SQLAlchemy compiles only whitelisted entities, fields, relationships and functions with bound parameters. No agent-authored SQL, configuration tables, credentials or ingestion internals are exposed.

Counts and aggregates operate on the full qualifying dataset. Distinct entity counts are explicit to avoid join multiplication. LEFT joins retain unused skills. Calendar-month durations are estimates; merged PostgreSQL integer multiranges provide overlapping timeline coverage. Missing dates contribute no known duration and are disclosed rather than converted to zero.

Results contain typed columns, compact rows, criteria, matched vocabulary, totals, completeness, structured entity references and per-group scopes. Scope lineage includes only contributing joined/existence records; excluded records never qualify. RAG receives server-held opaque handles, filters before ranking and neighbor expansion, and excludes stale revisions. Skills are not standalone indexed sources. Parent-job context cannot establish a match for a sibling project.

The compiler bounds joins (8), expressions (180 nodes, depth 22), columns (20), page size (100), and complete output groups/rows (10,000). PostgreSQL retains its five-second statement timeout. Exceeding a limit is an explicit unsupported operation, not an empty result. Ordinary lists default to five rows; explicit complete compact lists use up to 100. Paginated totals and full scopes are computed before slicing. Ranking rows and relationship facts take precedence over long narratives in evidence budgets; omitted rows are disclosed.

Record reading returns detached current details and full relationship fields. Document reading uses current-revision extracted text, otherwise the current stored PDF. Transactions close before extraction. A killable subprocess limits extraction time; existing PDF page/decompression limits remain, with a two-million-character extracted-text ceiling. A read returns at most 20,000 characters and may target up to ten pages. Unreadable PDFs report an error, without stale text or embedding dependence.

The four-decision/eight-operation supervisor and 90-second research plus 30-second synthesis budgets remain. Database failures do not become zero counts or claims of absent career information. The Representative receives the verified evidence and places no citations in prose; the existing Sources footer remains the sole attribution display.

Existing saved JSON receives new defaults on load only when prior shipped prompt fingerprints match exactly. Customized prompts, model overrides, the independent RAG-only prompt and the enabled switch are preserved. Connection testing for the Database role now validates a native call using the real composable schema.

## Consequences

No career-data migration, re-ingestion, dependency or additional service is needed. The agent can compose new analytical questions from catalog capabilities, but cannot promise every conceivable calculation or read unsupported resources. Complex requests may need clarification or a narrower query. Full query lineage can be more expensive than simple page retrieval; bounded output, statement timeouts and the global operation budget constrain it.

Regression tests exercise SQL execution against PostgreSQL, grouped scope lineage, dates, documents and evidence preservation. A separate live-model evaluator uses independently authored SQL for rankings, employer aggregates and co-occurring skills, alongside document and timeline checks.
