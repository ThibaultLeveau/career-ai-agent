"""Authenticated download references for explicitly published resume PDFs."""

from typing import Literal

from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.security import cipher
from app.content.models import Document


class DownloadScope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    purpose: Literal["resume_download"] = "resume_download"
    document_id: int = Field(gt=0)


def download_token(document_id: int) -> str:
    scope = DownloadScope(document_id=document_id)
    return cipher().encrypt(scope.model_dump_json().encode()).decode()


def download_document_id(token: str) -> int:
    try:
        if not token or len(token) > 2048:
            raise ValueError("Invalid download token")
        return DownloadScope.model_validate_json(
            cipher().decrypt(token.encode())
        ).document_id
    except InvalidToken, ValidationError, ValueError:
        raise ValueError("This resume is no longer available.") from None


def eligible_resume(db: Session, document_id: int) -> Document | None:
    return db.scalar(
        select(Document)
        .where(
            Document.id == document_id,
            Document.document_type_key == "resume",
            Document.available_in_chat.is_(True),
        )
        .execution_options(populate_existing=True)
    )
