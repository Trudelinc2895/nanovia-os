FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir pip-audit \
    && pip-audit -r requirements.txt --vulnerability-service osv || true

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

ARG DEPLOY_SHA=unknown
LABEL org.opencontainers.image.revision=$DEPLOY_SHA

RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system appuser \
    && adduser --system --ingroup appuser appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY backend/ .
COPY shared/ /shared/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8010

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "2", "--no-proxy-headers"]
