# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /usr/local/bin/

WORKDIR /app/services

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.11-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    # Aplikacja działa wyłącznie z /app/services/.venv; systemowe narzędzia
    # instalacyjne to zbędna powierzchnia ataku (CVE w setuptools/_vendor).
    && python -m pip uninstall -y wheel setuptools pip \
    && groupadd --system --gid 1001 miplo \
    && useradd --system --uid 1001 --gid miplo --create-home miplo

WORKDIR /app

COPY --from=builder --chown=miplo:miplo /app/services/.venv /app/services/.venv
COPY --chown=miplo:miplo __init__.py /app/services/__init__.py
COPY --chown=miplo:miplo app/ /app/services/app/
COPY --chown=miplo:miplo scripts/ /app/services/scripts/

ENV PATH="/app/services/.venv/bin:${PATH}" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

USER miplo

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent --show-error "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["sh", "-c", "exec uvicorn services.app.server:app --host 0.0.0.0 --port ${PORT}"]
