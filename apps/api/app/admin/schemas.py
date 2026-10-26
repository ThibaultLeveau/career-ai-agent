from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

Provider = Literal["openai", "anthropic"]
Stage = Literal["chat", "embeddings", "reranking"]
Username = Annotated[
    str, Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
]
Password = Annotated[SecretStr, Field(min_length=12, max_length=1024)]
ModelName = Annotated[str, Field(max_length=128, pattern=r"^[a-zA-Z0-9_.:-]*$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    username: str = Field(max_length=64)
    password: SecretStr = Field(max_length=1024)


class Credentials(StrictModel):
    current_password: SecretStr = Field(max_length=1024)
    username: Username
    new_password: Password | None = None


class KeyInput(StrictModel):
    key: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator("key")
    @classmethod
    def valid_key(cls, value: SecretStr) -> SecretStr:
        if any(c.isspace() for c in value.get_secret_value()):
            raise ValueError("API keys cannot contain whitespace")
        return value


class Generation(StrictModel):
    provider: Provider = "openai"
    model: ModelName = ""
    max_output_tokens: int = Field(default=2048, ge=128, le=32768)


class Chat(Generation):
    system_prompt: str = Field(
        default="Answer questions about the portfolio owner using supplied context. "
        "If the context does not support an answer, say so. Do not invent details.",
        max_length=16000,
    )


class Embeddings(StrictModel):
    provider: Literal["openai"] = "openai"
    model: Literal["text-embedding-3-small", "text-embedding-3-large"] = (
        "text-embedding-3-small"
    )
    dimensions: int = Field(default=1536, ge=1, le=3072)

    @model_validator(mode="after")
    def valid_dimensions(self) -> Self:
        if self.model == "text-embedding-3-small" and self.dimensions > 1536:
            raise ValueError("This embedding model supports at most 1536 dimensions")
        return self


class Reranking(Generation):
    enabled: bool = False


class Retrieval(StrictModel):
    mode: Literal["hybrid", "semantic"] = "hybrid"
    candidate_count: int = Field(default=20, ge=1, le=100)
    context_count: int = Field(default=5, ge=1, le=100)
    window_size: int = Field(default=1, ge=0, le=5)

    @model_validator(mode="after")
    def valid_ranges(self) -> Self:
        if self.context_count > self.candidate_count:
            raise ValueError("Context count cannot exceed candidate count")
        return self


class Ingestion(StrictModel):
    chunk_size: int = Field(default=800, ge=100, le=8000)
    chunk_overlap: int = Field(default=100, ge=0, le=7999)
    max_retries: int = Field(default=3, ge=0, le=10)

    @model_validator(mode="after")
    def valid_ranges(self) -> Self:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size")
        return self


class RagSettings(StrictModel):
    chat: Chat = Field(default_factory=Chat)
    embeddings: Embeddings = Field(default_factory=Embeddings)
    reranking: Reranking = Field(default_factory=Reranking)
    retrieval: Retrieval = Field(default_factory=Retrieval)
    ingestion: Ingestion = Field(default_factory=Ingestion)


class SettingsPatch(StrictModel):
    chat: Chat | None = None
    embeddings: Embeddings | None = None
    reranking: Reranking | None = None
    retrieval: Retrieval | None = None
    ingestion: Ingestion | None = None


class ConnectionTest(StrictModel):
    settings: RagSettings
    key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)


class SessionInfo(StrictModel):
    username: str


class ProviderStatus(StrictModel):
    provider: Provider
    configured: bool


class TestResult(StrictModel):
    ok: bool = True
    message: str
