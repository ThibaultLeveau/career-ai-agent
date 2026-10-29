from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.chat.database import DatabaseQuery, QueryModel

Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
Entity = Literal["skills", "projects", "jobs", "documents"]


class Expression(QueryModel):
    field: str | None = Field(default=None, max_length=100)
    value: str | int | float | bool | None = Field(default=None)
    function: (
        Literal[
            "count",
            "count_distinct",
            "sum",
            "avg",
            "min",
            "max",
            "add",
            "subtract",
            "multiply",
            "divide",
            "coalesce",
            "lower",
            "year",
            "month",
            "duration_months",
            "coverage_months",
        ]
        | None
    ) = None
    args: list[Expression] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def shape(self) -> Self:
        choices = int(self.field is not None) + int(self.function is not None)
        choices += int("value" in self.model_fields_set)
        if choices != 1 or (self.args and self.function is None):
            raise ValueError("Use exactly one of field, value, or function with args")
        if isinstance(self.value, str) and len(self.value) > 4000:
            raise ValueError("Literal text exceeds 4000 characters")
        return self


class Predicate(QueryModel):
    op: Literal[
        "and",
        "or",
        "not",
        "eq",
        "ne",
        "lt",
        "lte",
        "gt",
        "gte",
        "in",
        "contains",
        "skill_matches",
        "is_null",
        "exists",
    ]
    left: Expression | None = None
    right: Expression | None = None
    values: list[str | int | float | bool] = Field(default_factory=list, max_length=100)
    children: list[Predicate] = Field(default_factory=list, max_length=20)
    relationship: str | None = Field(default=None, max_length=100)
    alias: Name | None = None
    where: Predicate | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        present = self.model_fields_set - {"op"}
        allowed = {
            "and": {"children"},
            "or": {"children"},
            "not": {"children"},
            "exists": {"relationship", "alias", "where"},
            "in": {"left", "values"},
            "is_null": {"left"},
        }.get(self.op, {"left", "right"})
        if present - allowed:
            raise ValueError(f"Unexpected arguments for {self.op}")
        if self.op in {"and", "or", "not"}:
            if not self.children or (self.op == "not" and len(self.children) != 1):
                raise ValueError("Boolean predicates need children; NOT needs one")
        elif self.op == "exists":
            if not self.relationship or not self.alias:
                raise ValueError("EXISTS needs relationship and alias")
        elif self.left is None or (
            self.op not in {"in", "is_null"} and self.right is None
        ):
            raise ValueError("Comparison needs left and right expressions")
        return self


class Join(QueryModel):
    relationship: str = Field(max_length=100, description="Existing alias.relationship")
    alias: Name
    kind: Literal["inner", "left"] = "inner"
    where: Predicate | None = Field(
        default=None,
        description="Additional join condition; preserves unmatched left rows",
    )


class Selection(QueryModel):
    name: Name
    expression: Expression


class Ordering(QueryModel):
    column: Name = Field(description="Name of a selected output column")
    direction: Literal["asc", "desc"] = "asc"


class SelectQuery(QueryModel):
    entity: Entity
    alias: Name = "root"
    joins: list[Join] = Field(default_factory=list, max_length=8)
    select: list[Selection] = Field(min_length=1, max_length=20)
    where: Predicate | None = None
    group_by: list[Expression] = Field(default_factory=list, max_length=8)
    having: Predicate | None = None
    order_by: list[Ordering] = Field(default_factory=list, max_length=8)
    distinct: bool = False
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=5, ge=1, le=100)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        pending = [(self.model_dump(exclude_none=True), 0)]
        nodes = 0
        while pending:
            item, depth = pending.pop()
            if isinstance(item, dict):
                nodes += 1
                if nodes > 180 or depth > 22:
                    raise ValueError("Query exceeds expression complexity limit")
                pending.extend((value, depth + 1) for value in item.values())
            elif isinstance(item, list):
                pending.extend((value, depth + 1) for value in item)
        names = [item.name for item in self.select]
        if len(names) != len(set(names)):
            raise ValueError("Output column names must be unique")
        return self


class ReadRequest(QueryModel):
    entity: Entity
    ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=20)
    offset: int = Field(default=0, ge=0, le=2000000)
    max_chars: int = Field(default=8000, ge=100, le=20000)
    page_start: int | None = Field(default=None, ge=1, le=500)
    page_end: int | None = Field(default=None, ge=1, le=500)

    @model_validator(mode="after")
    def page_range(self) -> Self:
        if self.page_end is not None and self.page_start is None:
            raise ValueError("page_end requires page_start")
        if self.page_start is not None:
            if self.entity != "documents":
                raise ValueError("Pages apply only to documents")
            if self.page_end is None:
                self.page_end = self.page_start
            if not 0 <= self.page_end - self.page_start < 10:
                raise ValueError("Read between one and ten pages per operation")
        return self


class DatabaseRequest(DatabaseQuery):
    operation: Literal["records", "query", "read"] = "records"
    query: SelectQuery | None = None
    read: ReadRequest | None = None

    @model_validator(mode="after")
    def operation_payload(self) -> Self:
        expected = {"query": "query", "read": "read"}.get(self.operation)
        if expected:
            if getattr(self, expected) is None:
                raise ValueError(f"{self.operation} requires its {expected} payload")
            if self.model_fields_set - {"operation", expected}:
                raise ValueError("Put query/read options inside its payload")
        elif self.query is not None or self.read is not None:
            raise ValueError("Select the query or read operation for its payload")
        return self
