import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.admin.security import check_origin
from app.chat import components
from app.chat.providers import UNAVAILABLE, ChatError
from app.chat.schemas import ChatRequest
from app.chat.service import answer, prepare
from app.db import get_session

router = APIRouter(dependencies=[Depends(check_origin)])
logger = logging.getLogger(__name__)


@router.post(
    "/chat/components/page", response_model=components.ProjectList | components.JobList
)
def component_page(
    data: components.PageRequest, db: Annotated[Session, Depends(get_session)]
):
    try:
        return components.page(db, data)
    except components.ComponentError as error:
        raise HTTPException(400, str(error)) from None
    except SQLAlchemyError:
        raise HTTPException(
            503, "This list could not be loaded. Please try again."
        ) from None


@router.post("/chat")
def chat(data: ChatRequest, db: Annotated[Session, Depends(get_session)]):
    try:
        prepared = prepare(db)
        if data.action and not prepared.config.agents.enabled:
            raise ChatError(
                "This detail view is unavailable. Please ask a new question.", 409
            )
    except ChatError as error:
        raise HTTPException(error.status, str(error)) from None
    except SQLAlchemyError, ValidationError:
        logger.warning("Career chat could not load its context or configuration")
        raise HTTPException(503, UNAVAILABLE) from None
    return StreamingResponse(
        answer(prepared, data),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
