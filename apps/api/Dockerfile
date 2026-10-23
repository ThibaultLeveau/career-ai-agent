FROM ghcr.io/astral-sh/uv:0.13.5 AS uv
FROM python:3.14.9-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=uv /uv /uvx /usr/local/bin/
RUN useradd --create-home --uid 10001 app
COPY pyproject.toml uv.lock ./

FROM base AS development
RUN uv sync --locked
COPY --chown=app:app . .
RUN chown app:app /app
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS dependencies
RUN uv sync --locked --no-dev

FROM python:3.14.9-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY alembic.ini ./
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
