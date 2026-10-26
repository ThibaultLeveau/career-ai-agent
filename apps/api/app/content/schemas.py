from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=8000)]
Month = Annotated[str, Field(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RecordOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    ingestion: dict


class TimelineInput(Input):
    start_month: Month | None = None
    end_month: Month | None = None
    ongoing: bool = False
    summary: Text = ""

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        if self.ongoing and self.end_month:
            raise ValueError("Ongoing entries cannot have an end month")
        if self.start_month and self.end_month and self.end_month < self.start_month:
            raise ValueError("End month must be on or after start month")
        return self


class JobInput(TimelineInput):
    title: Name
    company: Name
    location: str = Field(default="", max_length=200)
    responsibilities: Text = ""
    achievements: Text = ""


class JobOutput(JobInput, RecordOutput):
    project_count: int


class SkillInput(Input):
    keyword: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]


class SkillOutput(SkillInput, RecordOutput):
    pass


class ProjectInput(TimelineInput):
    name: Name
    role: str = Field(default="", max_length=200)
    description: Text = ""
    outcomes: Text = ""
    website_url: str = Field(default="", max_length=2048)
    repository_url: str = Field(default="", max_length=2048)
    job_id: int | None = Field(default=None, gt=0)
    skill_ids: list[Annotated[int, Field(gt=0)]] = Field(
        default_factory=list, max_length=500
    )

    @field_validator("website_url", "repository_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        if value:
            TypeAdapter(HttpUrl).validate_python(value)
        return value


class ProjectOutput(RecordOutput):
    name: str
    role: str
    start_month: str | None
    end_month: str | None
    ongoing: bool
    summary: str
    description: str
    outcomes: str
    website_url: str
    repository_url: str
    job_id: int | None
    kind: Literal["professional", "personal"]
    skills: list[SkillOutput]


class DocumentInput(Input):
    title: Name


class DocumentOutput(RecordOutput):
    title: str
    filename: str
    size: int
