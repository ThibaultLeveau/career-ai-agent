from app.content.models import Document, Job, Project, Skill

MODELS = {"skills": Skill, "projects": Project, "jobs": Job, "documents": Document}
FIELDS = {
    "skills": {"id": "number", "keyword": "text"},
    "projects": {
        "id": "number",
        "name": "text",
        "role": "text",
        "job_id": "number",
        "start_month": "month",
        "end_month": "month",
        "ongoing": "boolean",
        "summary": "text",
        "description": "text",
        "outcomes": "text",
        "website_url": "text",
        "repository_url": "text",
        "kind": "text",
    },
    "jobs": {
        "id": "number",
        "title": "text",
        "company": "text",
        "location": "text",
        "start_month": "month",
        "end_month": "month",
        "ongoing": "boolean",
        "summary": "text",
        "responsibilities": "text",
        "achievements": "text",
    },
    "documents": {
        "id": "number",
        "title": "text",
        "filename": "text",
        "size": "number",
    },
}
RELATIONS = {
    ("skills", "projects"): "projects",
    ("projects", "skills"): "skills",
    ("projects", "job"): "jobs",
    ("jobs", "projects"): "projects",
}


def catalog() -> dict:
    return {
        "entities": {
            name: {
                "fields": fields,
                "relationships": {
                    rel: target
                    for (source, rel), target in RELATIONS.items()
                    if source == name
                },
            }
            for name, fields in FIELDS.items()
        },
        "operations": {
            "records": "Existing exact projects/jobs filters and pagination.",
            "query": (
                "Select fields, join relationships, filter, group, "
                "aggregate, sort. Use this for skill lists/rankings and "
                "analytics. Fields use alias.field; order_by uses "
                "selected column names. HAVING can reference selected "
                "names. COUNT DISTINCT entity.id avoids join duplication. "
                "count() counts joined rows. Include group keys in "
                "group_by. Left joins include unlinked/unused records. "
                "'all' requests use limit=100 and continue if has_more."
            ),
            "read": (
                "Read current record details with complete skills and "
                "relationships, or document text, without embeddings. "
                "Text is paged by offset/max_chars; optional document "
                "page_start/page_end. Follow next_offset when text is "
                "incomplete."
            ),
        },
        "expressions": {
            "field": {"field": "alias.field"},
            "literal": {"value": "literal value"},
            "function": {"function": "count_distinct", "args": [{"field": "p.id"}]},
            "aggregates": "count, count_distinct, sum, avg, min, max, coverage_months",
            "scalar_functions": (
                "add/subtract/multiply/divide (2 numeric args), coalesce, "
                "lower, year, month, duration_months"
            ),
            "duration": (
                "duration_months(start_month,end_month,ongoing) counts "
                "inclusive calendar months. coverage_months uses the same "
                "3 args and merges overlapping intervals within each "
                "group. Unknown periods are excluded, not treated as zero "
                "experience. Current month is supplied by the server."
            ),
        },
        "join_filters": (
            "A join can have its own where predicate, applied in ON. Use this "
            "with LEFT joins for filtered counts that must retain zero groups. "
            "For company-specific skill counts, LEFT JOIN skills.projects with "
            "an EXISTS on project.job filtered by company in the join condition."
        ),
        "predicates": (
            "and/or/not with children; comparisons eq/ne/lt/lte/gt/gte "
            "with left/right expressions; in with left/values; is_null "
            "with left; literal case-insensitive contains; skill_matches "
            "for vocabulary matching with short-token boundaries. exists "
            "uses relationship, alias, and optional where. Use a single "
            "correlated project EXISTS for multiple skills that must "
            "occur on the same project."
        ),
        "scope": (
            "Queries return complete result-set and per-row/group handles "
            "for scoped RAG. Only actual contributing "
            "project/job/document records qualify. Skills are structured "
            "facts, not indexed documents. A skill-only query has no "
            "semantic scope unless projects are joined."
        ),
        "example": {
            "operation": "query",
            "query": {
                "entity": "skills",
                "alias": "s",
                "joins": [{"relationship": "s.projects", "alias": "p", "kind": "left"}],
                "select": [
                    {"name": "skill", "expression": {"field": "s.keyword"}},
                    {
                        "name": "project_count",
                        "expression": {
                            "function": "count_distinct",
                            "args": [{"field": "p.id"}],
                        },
                    },
                ],
                "group_by": [{"field": "s.id"}, {"field": "s.keyword"}],
                "order_by": [
                    {"column": "project_count", "direction": "desc"},
                    {"column": "skill"},
                ],
                "limit": 100,
            },
        },
    }
