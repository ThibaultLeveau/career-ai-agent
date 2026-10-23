from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.admin import router as admin_router
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
app.include_router(admin_router)


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": item["loc"], "msg": item["msg"]} for item in error.errors()
            ]
        },
    )
