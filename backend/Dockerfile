# Backend image: serves the API (`radar-api`) or runs the worker (`radar-worker`) depending on the command.
# Build context is the repository root so the golden set in evals/ is available to the seed script.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    RADAR_EVALS_DIR=/app/evals

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY evals/ /app/evals/
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && radar-seed && radar-api"]

# --- optional: JS rendering for sources flagged requires_js ---------------------------------
FROM base AS js
RUN uv sync --frozen --no-dev --extra js && playwright install --with-deps chromium
