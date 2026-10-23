from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.admin.models import Administrator, RagConfiguration
from app.admin.schemas import Credentials, RagSettings
from app.admin.security import cipher, password_hasher
from app.core.config import get_settings
from app.db import get_engine


def bootstrap(db: Session) -> None:
    cipher()
    if not db.scalar(select(Administrator.id)):
        settings = get_settings()
        initial = Credentials(
            username=settings.admin_initial_username,
            current_password="",
            new_password=settings.admin_initial_password,
        )
        db.execute(
            insert(Administrator)
            .values(
                id=1,
                username=initial.username,
                password_hash=password_hasher.hash(
                    initial.new_password.get_secret_value()
                ),
                failed_attempts=0,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
    db.execute(
        insert(RagConfiguration)
        .values(id=1, configuration=RagSettings().model_dump())
        .on_conflict_do_nothing(index_elements=["id"])
    )
    db.commit()


if __name__ == "__main__":
    try:
        with Session(get_engine()) as session:
            bootstrap(session)
    except ValidationError, ValueError:
        raise SystemExit(
            "Set a valid SETTINGS_ENCRYPTION_KEY and, for the first account, "
            "ADMIN_INITIAL_USERNAME and ADMIN_INITIAL_PASSWORD (12+ characters)."
        ) from None
