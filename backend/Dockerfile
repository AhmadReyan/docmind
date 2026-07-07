# syntax=docker/dockerfile:1

###############################################################################
# Stage 1: resolve dependencies with uv and pre-download the embedding model
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# uv.lock may not exist yet early in development -- the trailing wildcard makes
# the COPY tolerant. When the lockfile is present, `uv sync` honors it (and only
# re-resolves if pyproject.toml changed); without it, uv resolves from scratch.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

# Bake the fastembed model (BAAI/bge-small-en-v1.5, ~130MB) into the image so
# `docker compose up` never downloads it at runtime. World-readable so the
# non-root runtime user can load it.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache
RUN /opt/venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')" \
    && chmod -R a+rX /opt/fastembed_cache

###############################################################################
# Stage 2: runtime
###############################################################################
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/opt/fastembed_cache

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app \
    && mkdir -p /data/uploads \
    && chown -R app:app /data/uploads

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/fastembed_cache /opt/fastembed_cache

COPY --chown=app:app pyproject.toml alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app evals ./evals
COPY --chown=app:app seed_data ./seed_data

USER app

EXPOSE 8000

# docker-compose overrides this per service (api: alembic upgrade + seed +
# uvicorn; worker: arq app.ingestion.worker.WorkerSettings).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
