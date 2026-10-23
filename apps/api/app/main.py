from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router
from app.db import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="Career AI API", lifespan=lifespan)
app.include_router(router)
