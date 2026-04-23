# ---- Backend (FastAPI) production image ----------------------------------
# Multi-stage build produces a small (~200 MB) runtime image.
#   Stage 1  builder   compiles wheels against pinned requirements.txt
#   Stage 2  runtime   copies site-packages + source, runs under non-root user
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt ./
# `emergentintegrations` is published on a private wheelhouse. It is optional
# for self-hosted deployments and is fetched only when auto-translation is on.
RUN pip install --prefix=/install \
    --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ \
    -r requirements.txt

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8001

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

COPY --from=builder /install /usr/local
WORKDIR /app
COPY . /app
RUN chown -R app:app /app

USER app
EXPOSE 8001

# Health endpoint comes from the FastAPI app itself (GET /api/healthz).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/healthz" || exit 1

# Workers scale horizontally. For a single VPS, WEB_CONCURRENCY=2 is a good
# starting point; PaaS typically sets this via its own env injection.
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'"]
