# Database Agent query capabilities

The server supplies the current catalog with every Database specialist request. Editable prompts guide behavior but cannot change permissions, supported functions or budgets.

## Operations

- `records`: existing exact project/job filters, Boolean skill expressions, dates, company, role and pagination. Five results by default.
- `query`: choose `entity`, an `alias`, `select` expressions, optional relationship `joins`, Boolean `where`, `group_by`, `having`, `order_by`, `offset` and `limit`. Limits are five by default and at most 100. Use aggregates directly rather than querying each skill separately.
- `read`: choose an entity and up to 20 IDs. Returns current structured details and relationships, or document text. `offset`/`max_chars` page through narrative text (20,000 characters maximum across records); document `page_start`/`page_end` restrict to at most ten pages. Embeddings are unnecessary.

## Composing queries

Fields use `alias.field`. Relationships are `skills.projects`, `projects.skills`, `projects.job`, and `jobs.projects`, referenced through an existing alias. Each join has its own alias and `inner` or `left` kind. EXISTS accepts a relationship, alias and nested filter, so multiple skill requirements can hold on the same project without multiplying rows. NOT EXISTS finds records without relationships.

Expressions select fields, literal values, or functions with expression arguments. Aggregates are `count`, `count_distinct`, `sum`, `avg`, `min`, `max`, and `coverage_months`. Scalars include `add`, `subtract`, `multiply`, `divide`, `coalesce`, `lower`, `year`, `month`, and `duration_months`. Division by zero returns unknown. `year` and `month` group stored month dates. Both duration functions accept start month, end month and ongoing flag; coverage merges overlapping periods within a group. Inclusive calendar months are estimates, not day-level durations.

Filters support AND/OR/NOT, comparisons, IN, IS NULL, literal case-insensitive contains and catalog-aware `skill_matches`. Literal `%` and `_` do not become wildcards. Short skill terms use token boundaries: AI matches Agentic AI but not OpenAI. Broader semantic expansions must be separate related searches.

To rank every skill, start with skills, LEFT JOIN projects, group by skill ID and keyword, count distinct project IDs, order count descending then keyword (ID breaks ties), and request 100 rows. Unused skills receive zero. For company counts, start with jobs and join projects, grouping by company; count distinct IDs so multiple skills do not duplicate projects/jobs.

Only career fields are exposed; document bytes and ingestion state are accessed exclusively through bounded document reading. Unsupported fields/functions and invalid types receive validation feedback. A failed or unsupported operation is not evidence that career data is missing.

## Evidence and pagination

`total` is the number of output rows/groups, not necessarily a project count. Read aggregate columns for entity counts. `complete`, `offset`, `has_more`, `returned_count`, text completeness and context limitations describe what the model actually received. A complete-result handle scopes all qualifying records, independently of the page; each displayed row/group has its own scope. Structured entity references accompany compact table rows. Empty scopes produce no semantic evidence.

Explicit complete lists must retain every compact row, continuing pages within the eight-operation/four-decision budget. If the budget or context prevents completion, say what remains omitted. Source attribution appears only in the Sources footer.

## Evaluation

Run `python scripts/evaluate_career_queries.py --mode both` inside the API container. `--case skills-ranking-en` reproduces the screenshot; additional cases cover French rankings, employers, Python co-occurrence, document reading and timeline coverage. The tool makes read-only production queries and real provider requests, prints JSONL results, and never changes saved settings. Inspect answer completeness, dates and document claims alongside the independent SQL comparisons and recorded latency/model usage. Run `sh scripts/check.sh` before deploying.

A join may also specify its own `where` condition, applied to the join rather than the final result. For example, a LEFT project join with a company-filtered job EXISTS counts only that company's projects while retaining every skill with zero where appropriate.
