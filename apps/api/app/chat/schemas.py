from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def complete_turns(self) -> Self:
        if len(self.history) % 2 or any(
            item.role != ("user" if index % 2 == 0 else "assistant")
            for index, item in enumerate(self.history)
        ):
            raise ValueError("History must contain completed user/assistant pairs")
        if sum(len(item.content) for item in self.history) > 24000:
            raise ValueError("Conversation history is too long")
        return self


class Citation(BaseModel):
    id: str
    label: str
    source_type: Literal["job", "project", "document"]
    page_start: int | None = None
    page_end: int | None = None
