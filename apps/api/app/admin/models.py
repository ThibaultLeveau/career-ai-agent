from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Administrator(Base):
    __tablename__ = "administrator"
    __table_args__ = (CheckConstraint("id = 1", name="single_administrator"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    failed_attempts: Mapped[int] = mapped_column(default=0)
    login_window: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminSession(Base):
    __tablename__ = "admin_session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    administrator_id: Mapped[int] = mapped_column(ForeignKey("administrator.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ProviderKey(Base):
    __tablename__ = "provider_key"
    __table_args__ = (
        CheckConstraint("provider IN ('openai', 'anthropic')", name="allowed_provider"),
    )

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    encrypted_key: Mapped[str]


class RagConfiguration(Base):
    __tablename__ = "rag_configuration"
    __table_args__ = (CheckConstraint("id = 1", name="single_configuration"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration: Mapped[dict] = mapped_column(JSON)
