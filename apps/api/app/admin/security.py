import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.admin.models import Administrator, AdminSession
from app.core.config import get_settings
from app.db import get_session

COOKIE = "career_admin"
SESSION_SECONDS = 12 * 60 * 60
password_hasher = PasswordHasher()
Database = Annotated[Session, Depends(get_session)]


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def matches(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerificationError:
        return False


def cipher() -> Fernet:
    return Fernet(get_settings().settings_encryption_key.get_secret_value().encode())


def check_origin(request: Request) -> None:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") != get_settings().app_origin.rstrip("/"):
            raise HTTPException(403, "Request origin is not allowed")


def require_admin(request: Request, db: Database) -> Administrator:
    token = request.cookies.get(COOKIE, "")
    session = db.get(AdminSession, digest(token)) if token else None
    if not session or session.expires_at <= datetime.now(UTC):
        raise HTTPException(401, "Please sign in")
    administrator = db.get(Administrator, session.administrator_id)
    if administrator is None:
        raise HTTPException(401, "Please sign in")
    return administrator


Admin = Annotated[Administrator, Depends(require_admin)]


def create_session(db: Session, administrator: Administrator) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AdminSession(
            token_hash=digest(token),
            administrator_id=administrator.id,
            expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_SECONDS),
        )
    )
    return token
