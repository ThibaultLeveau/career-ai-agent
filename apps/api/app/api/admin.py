from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select

from app.admin.models import Administrator, AdminSession, ProviderKey, RagConfiguration
from app.admin.providers import test_connection
from app.admin.schemas import (
    ConnectionTest,
    Credentials,
    KeyInput,
    Login,
    Provider,
    ProviderStatus,
    RagSettings,
    SessionInfo,
    SettingsPatch,
    Stage,
    TestResult,
)
from app.admin.security import (
    COOKIE,
    SESSION_SECONDS,
    Admin,
    Database,
    check_origin,
    cipher,
    create_session,
    digest,
    matches,
    password_hasher,
)
from app.core.config import get_settings

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(check_origin)]
)


@router.post("/login", response_model=SessionInfo)
def login(data: Login, response: Response, db: Database) -> SessionInfo:
    administrator = db.scalar(select(Administrator).with_for_update())
    if administrator is None:
        raise HTTPException(503, "Administrator setup is incomplete")
    now = datetime.now(UTC)
    if not administrator.login_window or administrator.login_window < now - timedelta(
        minutes=15
    ):
        administrator.login_window = now
        administrator.failed_attempts = 0
    if administrator.failed_attempts >= 5:
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    valid = matches(administrator.password_hash, data.password.get_secret_value())
    if not valid or administrator.username != data.username:
        administrator.failed_attempts += 1
        db.commit()
        raise HTTPException(401, "Invalid username or password")
    administrator.failed_attempts = 0
    db.execute(delete(AdminSession).where(AdminSession.expires_at <= now))
    token = create_session(db, administrator)
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=get_settings().app_origin.startswith("https://"),
        samesite="lax",
    )
    return SessionInfo(username=administrator.username)


@router.get("/session", response_model=SessionInfo)
def session_info(administrator: Admin) -> SessionInfo:
    return SessionInfo(username=administrator.username)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Database) -> None:
    db.execute(
        delete(AdminSession).where(
            AdminSession.token_hash == digest(request.cookies.get(COOKIE, ""))
        )
    )
    db.commit()
    response.delete_cookie(COOKIE)


@router.put("/credentials", status_code=204)
def update_credentials(
    data: Credentials, response: Response, administrator: Admin, db: Database
) -> None:
    administrator = db.scalar(
        select(Administrator)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not matches(
        administrator.password_hash, data.current_password.get_secret_value()
    ):
        raise HTTPException(400, "Current password is incorrect")
    administrator.username = data.username
    if data.new_password:
        administrator.password_hash = password_hasher.hash(
            data.new_password.get_secret_value()
        )
    db.execute(delete(AdminSession))
    db.commit()
    response.delete_cookie(COOKIE)


@router.get("/providers", response_model=list[ProviderStatus])
def provider_status(administrator: Admin, db: Database) -> list[ProviderStatus]:
    configured = set(db.scalars(select(ProviderKey.provider)))
    return [
        ProviderStatus(provider=provider, configured=provider in configured)
        for provider in ("openai", "anthropic")
    ]


@router.put("/providers/{provider}", status_code=204)
def save_key(provider: Provider, data: KeyInput, administrator: Admin, db: Database):
    db.merge(
        ProviderKey(
            provider=provider,
            encrypted_key=cipher()
            .encrypt(data.key.get_secret_value().encode())
            .decode(),
        )
    )
    db.commit()


@router.delete("/providers/{provider}", status_code=204)
def remove_key(provider: Provider, administrator: Admin, db: Database) -> None:
    db.execute(delete(ProviderKey).where(ProviderKey.provider == provider))
    db.commit()


@router.get("/settings", response_model=RagSettings)
def read_settings(administrator: Admin, db: Database) -> RagSettings:
    saved = db.get(RagConfiguration, 1)
    return RagSettings.model_validate(saved.configuration) if saved else RagSettings()


@router.put("/settings", response_model=RagSettings)
def save_settings(data: RagSettings, administrator: Admin, db: Database) -> RagSettings:
    db.scalar(
        select(RagConfiguration).where(RagConfiguration.id == 1).with_for_update()
    )
    db.merge(RagConfiguration(id=1, configuration=data.model_dump()))
    db.commit()
    return data


@router.patch("/settings", response_model=RagSettings)
def patch_settings(
    data: SettingsPatch, administrator: Admin, db: Database
) -> RagSettings:
    saved = db.scalar(
        select(RagConfiguration).where(RagConfiguration.id == 1).with_for_update()
    )
    current = (
        RagSettings.model_validate(saved.configuration).model_dump()
        if saved
        else RagSettings().model_dump()
    )
    current.update(data.model_dump(exclude_none=True, exclude_unset=True))
    result = RagSettings.model_validate(current)
    db.merge(RagConfiguration(id=1, configuration=result.model_dump()))
    db.commit()
    return result


@router.post("/test/{stage}", response_model=TestResult)
def check_connection(
    stage: Stage, data: ConnectionTest, administrator: Admin, db: Database
) -> TestResult:
    return test_connection(stage, data, db)
