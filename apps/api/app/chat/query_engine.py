import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Integer,
    and_,
    case,
    cast,
    distinct,
    func,
    literal,
    not_,
    or_,
    select,
    true,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import FunctionElement

from app.chat.database import matches_term
from app.chat.query_catalog import FIELDS, MODELS, RELATIONS
from app.chat.query_schema import Expression, Predicate, SelectQuery
from app.content.models import Skill, project_skill


class Coverage(FunctionElement):
    type = Integer()
    inherit_cache = True


@compiles(Coverage, "postgresql")
def compile_coverage(element, compiler, **kwargs):
    value = compiler.process(list(element.clauses)[0], **kwargs)
    return (
        "(SELECT SUM(upper(period) - lower(period)) "
        f"FROM unnest(range_agg({value})) AS period)"
    )


@dataclass
class Value:
    sql: object
    type: str
    aggregate: bool = False
    free: frozenset[str] = frozenset()


def key(expression: Expression) -> str:
    return expression.model_dump_json(exclude_unset=True)


def scalar(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def references(value) -> set[tuple[str, int]]:
    if isinstance(value, list):
        if (
            len(value) == 2
            and isinstance(value[0], str)
            and value[0] in ("skills", "projects", "jobs", "documents")
        ):
            return {(value[0], value[1])} if isinstance(value[1], int) else set()
        return set().union(*(references(item) for item in value)) if value else set()
    return set()


class Compiler:
    def __init__(self, query: SelectQuery, vocabulary: list[str]):
        self.query = query
        self.vocabulary = vocabulary
        root = MODELS[query.entity].__table__.alias(query.alias)
        self.aliases = {query.alias: (query.entity, root)}
        self.from_clause = root
        self.witnesses = []
        self.durations = []
        self.outputs = {}
        self.skill_matches = {}
        self.expression_cache = {}
        self.group_keys = {key(item) for item in query.group_by}
        self.serial = 0
        for join in query.joins:
            parent, child, source, target, condition = self.relationship(
                join.relationship, join.alias
            )
            if source is not child:
                bridge, parent_condition, child_condition = condition
                self.from_clause = self.from_clause.join(
                    bridge, parent_condition, isouter=join.kind == "left"
                )
                condition = child_condition
            self.aliases[join.alias] = (target, child)
            if join.where is not None:
                extra = self.predicate(join.where)
                if extra.aggregate:
                    raise ValueError("Join conditions cannot aggregate")
                condition = and_(condition, extra.sql)
            self.from_clause = self.from_clause.join(
                child, condition, isouter=join.kind == "left"
            )

    def relationship(self, path, name):
        if name in self.aliases:
            raise ValueError(f"Alias {name} is already in use")
        parts = path.split(".")
        if len(parts) != 2 or parts[0] not in self.aliases:
            raise ValueError("Relationships use existing_alias.relationship")
        entity, parent = self.aliases[parts[0]]
        target = RELATIONS.get((entity, parts[1]))
        if target is None:
            raise ValueError(f"Unknown relationship {path}; use the career catalog")
        child = MODELS[target].__table__.alias(name)
        if {entity, target} == {"skills", "projects"}:
            self.serial += 1
            bridge = project_skill.alias(f"_link_{self.serial}")
            parent_key = "skill_id" if entity == "skills" else "project_id"
            child_key = "project_id" if target == "projects" else "skill_id"
            parent_condition = bridge.c[parent_key] == parent.c.id
            child_condition = bridge.c[child_key] == child.c.id
            source = bridge.join(child, child_condition)
            return (
                parent,
                child,
                source,
                target,
                (bridge, parent_condition, child_condition),
            )
        condition = (
            parent.c.job_id == child.c.id
            if entity == "projects"
            else child.c.job_id == parent.c.id
        )
        return parent, child, child, target, condition

    def expression(self, expression: Expression, outputs=False) -> Value:
        cache_key = (
            key(expression),
            tuple((a, id(t)) for a, (_, t) in self.aliases.items()),
        )
        if cache_key not in self.expression_cache:
            value = self._expression(expression, outputs)
            if key(expression) in self.group_keys and not value.aggregate:
                value = Value(value.sql, value.type, free=frozenset([key(expression)]))
            self.expression_cache[cache_key] = value
        return self.expression_cache[cache_key]

    def _expression(self, expression: Expression, outputs=False) -> Value:
        if expression.field is not None:
            if outputs and expression.field in self.outputs:
                return self.outputs[expression.field]
            parts = expression.field.split(".")
            if len(parts) != 2 or parts[0] not in self.aliases:
                raise ValueError(f"Unknown field {expression.field}; use alias.field")
            entity, table = self.aliases[parts[0]]
            kind = FIELDS[entity].get(parts[1])
            if kind is None:
                raise ValueError(
                    f"Field {expression.field} is not in the career catalog"
                )
            sql = (
                case((table.c.job_id.is_(None), "personal"), else_="professional")
                if parts[1] == "kind"
                else table.c[parts[1]]
            )
            return Value(sql, kind, free=frozenset([key(expression)]))
        if expression.function is None:
            value = expression.value
            kind = (
                "null"
                if value is None
                else "boolean"
                if isinstance(value, bool)
                else "number"
                if isinstance(value, (int, float))
                else "text"
            )
            return Value(literal(value), kind)
        name = expression.function
        args = [self.expression(item, outputs) for item in expression.args]
        aggregate = name in {
            "count",
            "count_distinct",
            "sum",
            "avg",
            "min",
            "max",
            "coverage_months",
        }
        if aggregate and any(item.aggregate for item in args):
            raise ValueError("Nested aggregate functions are not supported")
        free = frozenset().union(*(item.free for item in args))
        any_aggregate = aggregate or any(item.aggregate for item in args)

        def require(count, kinds=None):
            if len(args) != count or (
                kinds and any(item.type not in kinds for item in args)
            ):
                raise ValueError(
                    f"{name} requires {count} arguments "
                    f"of type {kinds or 'compatible fields'}"
                )

        if name == "count":
            if len(args) > 1:
                raise ValueError("count accepts zero or one argument")
            return Value(
                func.count(args[0].sql) if args else func.count(), "number", True
            )
        if name in {"count_distinct", "sum", "avg", "min", "max"}:
            require(1, {"number", "null"} if name in {"sum", "avg"} else None)
            if name in {"min", "max"} and args[0].type == "boolean":
                raise ValueError(f"{name} needs a number, text or date field")
            sql = (
                func.count(distinct(args[0].sql))
                if name == "count_distinct"
                else getattr(func, name)(args[0].sql)
            )
            return Value(
                sql,
                "number" if name in {"count_distinct", "avg"} else args[0].type,
                True,
            )
        if name in {"add", "subtract", "multiply", "divide"}:
            require(2, {"number", "null"})
            a, b = (item.sql for item in args)
            sql = {
                "add": lambda: a + b,
                "subtract": lambda: a - b,
                "multiply": lambda: a * b,
                "divide": lambda: a / func.nullif(b, 0),
            }[name]()
            return Value(sql, "number", any_aggregate, free)
        if name == "coalesce":
            types = {item.type for item in args} - {"null"}
            if len(args) < 2 or len(types) > 1:
                raise ValueError("coalesce needs compatible arguments")
            return Value(
                func.coalesce(*(item.sql for item in args)),
                next(iter(types), "null"),
                any_aggregate,
                free,
            )
        if name == "lower":
            require(1, {"text"})
            return Value(func.lower(args[0].sql), "text", any_aggregate, free)
        if name in {"year", "month"}:
            require(1, {"month"})
            return Value(
                cast(
                    func.substr(
                        args[0].sql,
                        1 if name == "year" else 6,
                        4 if name == "year" else 2,
                    ),
                    Integer,
                ),
                "number",
                any_aggregate,
                free,
            )
        require(3)
        if [item.type for item in args] != ["month", "month", "boolean"] or any(
            item.aggregate for item in args
        ):
            raise ValueError(f"{name} needs start_month, end_month, ongoing fields")
        start, end, ongoing = (item.sql for item in args)
        today = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y-%m")
        finish = case((ongoing.is_(True), today), else_=end)

        def month_index(value):
            return cast(func.substr(value, 1, 4), Integer) * 12 + cast(
                func.substr(value, 6, 2), Integer
            )

        first, last = month_index(start), month_index(finish)
        valid = and_(start.is_not(None), finish.is_not(None), last >= first)
        duration = case((valid, last - first + 1))
        self.durations.append(duration)
        if name == "coverage_months":
            period = case((valid, func.int4range(first, last + 1, "[)")))
            return Value(Coverage(period), "number", True)
        return Value(duration, "number", False, free)

    def predicate(
        self, predicate: Predicate | None, outputs=False, witnesses=True
    ) -> Value:
        if predicate is None:
            return Value(true(), "boolean")
        op = predicate.op
        if op in {"and", "or", "not"}:
            children = [
                self.predicate(item, outputs, witnesses and op != "not")
                for item in predicate.children
            ]
            sql = (
                not_(children[0].sql)
                if op == "not"
                else (and_ if op == "and" else or_)(*(item.sql for item in children))
            )
            return Value(
                sql,
                "boolean",
                any(item.aggregate for item in children),
                frozenset().union(*(item.free for item in children)),
            )
        if op == "exists":
            if outputs:
                raise ValueError("Use relationship EXISTS in WHERE, not HAVING")
            parent, child, source, entity, relation = self.relationship(
                predicate.relationship, predicate.alias
            )
            condition = relation[1] if isinstance(relation, tuple) else relation
            original = self.witnesses
            self.witnesses = []
            self.aliases[predicate.alias] = (entity, child)
            try:
                where = self.predicate(predicate.where, witnesses=witnesses)
                if where.aggregate:
                    raise ValueError("EXISTS filters cannot aggregate")
                nested = self.witnesses
            finally:
                del self.aliases[predicate.alias]
                self.witnesses = original
            outer = [table for _, table in self.aliases.values()]
            stmt = (
                select(literal(1))
                .select_from(source)
                .where(condition, where.sql)
                .correlate(*outer)
            )
            if witnesses:
                values = [func.jsonb_build_array(entity, child.c.id)] + nested
                if values:
                    self.witnesses.append(
                        select(func.jsonb_agg(func.jsonb_build_array(*values)))
                        .select_from(source)
                        .where(condition, where.sql)
                        .correlate(*outer)
                        .scalar_subquery()
                    )
            return Value(stmt.exists(), "boolean")
        left = self.expression(predicate.left, outputs)
        if op == "is_null":
            return Value(left.sql.is_(None), "boolean", left.aggregate, left.free)
        if op == "in":
            for value in predicate.values:
                kind = (
                    "boolean"
                    if isinstance(value, bool)
                    else "number"
                    if isinstance(value, (int, float))
                    else "text"
                )
                if kind != left.type and not (left.type == "month" and kind == "text"):
                    raise ValueError("IN values must match the field type")
                if left.type == "month" and not re.fullmatch(
                    r"\d{4}-(0[1-9]|1[0-2])", str(value)
                ):
                    raise ValueError("Month values must use YYYY-MM")
            return Value(
                left.sql.in_(predicate.values), "boolean", left.aggregate, left.free
            )
        right = self.expression(predicate.right, outputs)
        compatible = (
            left.type == right.type
            or "null" in {left.type, right.type}
            or {left.type, right.type} == {"text", "month"}
        )
        if not compatible:
            raise ValueError("Comparison arguments have incompatible types")
        if left.type == "month" and right.type == "text":
            if not isinstance(predicate.right.value, str) or not re.fullmatch(
                r"\d{4}-(0[1-9]|1[0-2])", predicate.right.value
            ):
                raise ValueError(
                    "Compare month fields with YYYY-MM literals or other month fields"
                )
        if op in {"contains", "skill_matches"}:
            if (
                left.type != "text"
                or predicate.right.function
                or predicate.right.field
                or not isinstance(predicate.right.value, str)
            ):
                raise ValueError(f"{op} needs a text field and a literal string")
            if op == "skill_matches":
                field = predicate.left.field or ""
                alias, _, column = field.partition(".")
                if (
                    column != "keyword"
                    or self.aliases.get(alias, (None,))[0] != "skills"
                ):
                    raise ValueError("skill_matches applies to a skills keyword field")
                labels = [
                    word
                    for word in self.vocabulary
                    if matches_term(word, predicate.right.value)
                ]
                self.skill_matches[predicate.right.value] = labels
                sql = left.sql.in_(labels)
            else:
                sql = left.sql.icontains(predicate.right.value, autoescape=True)
        else:
            a, b = left.sql, right.sql
            if right.type == "null":
                if op not in {"eq", "ne"}:
                    raise ValueError("NULL only supports eq/ne or is_null")
                sql = a.is_(None) if op == "eq" else a.is_not(None)
            else:
                sql = {
                    "eq": lambda: a == b,
                    "ne": lambda: a != b,
                    "lt": lambda: a < b,
                    "lte": lambda: a <= b,
                    "gt": lambda: a > b,
                    "gte": lambda: a >= b,
                }[op]()
        return Value(
            sql, "boolean", left.aggregate or right.aggregate, left.free | right.free
        )

    def statement(self):
        query = self.query
        where = self.predicate(query.where)
        if where.aggregate:
            raise ValueError("Put aggregate filters in HAVING")
        selected = [self.expression(item.expression) for item in query.select]
        self.outputs = dict(
            zip((item.name for item in query.select), selected, strict=True)
        )
        groups = [self.expression(item) for item in query.group_by]
        if any(item.aggregate for item in groups):
            raise ValueError("Group keys cannot contain aggregates")
        having = self.predicate(query.having, outputs=True)
        aggregate = any(item.aggregate for item in selected) or having.aggregate
        grouped = aggregate or bool(groups) or query.distinct
        if query.distinct and aggregate:
            raise ValueError("Use GROUP BY for aggregates, not DISTINCT")
        if query.distinct:
            groups = selected
        group_keys = {key(item) for item in query.group_by}
        group_fields = group_keys
        if grouped and not query.distinct:
            for item, value in zip(query.select, selected, strict=True):
                if (
                    key(item.expression) not in group_keys
                    and not value.free <= group_fields
                ):
                    raise ValueError(
                        f"Selected column {item.name} must be grouped or aggregated"
                    )
            if not having.free <= group_fields:
                raise ValueError("HAVING references an ungrouped field")
        elif query.having is not None:
            raise ValueError("HAVING requires grouping or aggregation")
        refs = [
            func.jsonb_build_array(entity, table.c.id)
            for entity, table in self.aliases.values()
        ] + self.witnesses
        lineage = func.jsonb_build_array(*refs) if refs else literal("[]")
        if grouped:
            lineage = func.jsonb_agg(lineage)
        fields = [
            value.sql.label(item.name)
            for item, value in zip(query.select, selected, strict=True)
        ]
        fields.append(lineage.label("_lineage"))
        entity, root = self.aliases[query.alias]
        primary_key = key(Expression(field=f"{query.alias}.id"))
        if entity in {"projects", "jobs"} and (
            not grouped
            or primary_key in {key(item) for item in query.group_by}
            or (
                query.distinct
                and primary_key in {key(item.expression) for item in query.select}
            )
        ):
            fields.append(root.c.id.label("_primary_id"))
        if self.durations:
            unknown = or_(*(item.is_(None) for item in self.durations))
            fields.append(
                (func.bool_or(unknown) if grouped else unknown).label("_unknown_dates")
            )
        stmt = select(*fields).select_from(self.from_clause).where(where.sql)
        if groups:
            stmt = stmt.group_by(*(item.sql for item in groups))
        if query.having is not None:
            stmt = stmt.having(having.sql)
        for order in query.order_by:
            if order.column not in self.outputs:
                raise ValueError(f"Sort column {order.column} is not selected")
            sql = self.outputs[order.column].sql
            stmt = stmt.order_by(
                (sql.desc() if order.direction == "desc" else sql.asc()).nulls_last()
            )
        if groups:
            stmt = stmt.order_by(*(item.sql.asc().nulls_last() for item in groups))
        elif not aggregate:
            entity, root = self.aliases[query.alias]
            if not query.order_by and entity in {"projects", "jobs"}:
                stmt = stmt.order_by(
                    root.c.start_month.desc().nulls_last(), root.c.id.desc()
                )
            stmt = stmt.order_by(
                *(table.c.id.asc().nulls_last() for _, table in self.aliases.values())
            )
        return stmt.limit(10001), selected


def execute(db: Session, query: SelectQuery) -> dict:
    vocabulary = list(db.scalars(select(Skill.keyword)))
    compiler = Compiler(query, vocabulary)
    statement, columns = compiler.statement()
    all_rows = list(db.execute(statement).mappings())
    if len(all_rows) > 10000:
        raise ValueError(
            "The query exceeds 10000 result rows; narrow filters or aggregate"
        )
    total = len(all_rows)
    complete_refs = [references(row["_lineage"]) for row in all_rows]
    rag_refs = [{ref for ref in refs if ref[0] != "skills"} for refs in complete_refs]
    page = all_rows[query.offset : query.offset + query.limit]
    warnings = []
    if compiler.durations:
        warnings.append(
            "Durations use approximate inclusive calendar months; "
            "ongoing periods end in the current month. Coverage "
            "merges overlapping periods."
        )
        if any(row.get("_unknown_dates") for row in all_rows):
            warnings.append(
                "Some periods have unknown dates and are excluded "
                "from duration calculations; a missing duration is "
                "not zero experience."
            )
    names = [item.name for item in query.select]
    return {
        "entity": query.entity,
        "primary_refs": list(
            dict.fromkeys(
                (query.entity, row["_primary_id"])
                for row in all_rows
                if "_primary_id" in row
            )
        ),
        "page_primary_refs": list(
            dict.fromkeys(
                (query.entity, row["_primary_id"])
                for row in page
                if "_primary_id" in row
            )
        ),
        "total": total,
        "offset": query.offset,
        "limit": query.limit,
        "has_more": query.offset + len(page) < total,
        "complete": query.offset == 0 and len(page) == total,
        "columns": [
            {"name": name, "type": value.type}
            for name, value in zip(names, columns, strict=True)
        ],
        "rows": [[scalar(row[name]) for name in names] for row in page],
        "source_refs": sorted(set().union(*rag_refs)) if rag_refs else [],
        "group_refs": [
            sorted(refs) for refs in rag_refs[query.offset : query.offset + query.limit]
        ],
        "row_entities": [
            sorted(refs)
            for refs in complete_refs[query.offset : query.offset + query.limit]
        ],
        "applied_criteria": query.model_dump(exclude_none=True, exclude_unset=True),
        "skill_matches": compiler.skill_matches,
        "limitations": warnings,
    }
