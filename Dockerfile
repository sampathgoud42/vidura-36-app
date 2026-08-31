# Tradier Bot — full trading runtime, containerised for Cloud Run.
#
# The layout inside the image mirrors the project exactly, because the app
# derives everything from its own location: config.py resolves PROJECT_ROOT as
# parents[3] of backend/app/core/config.py, and main.py serves the SPA from
# <root>/frontend/dist. Move a directory here and those resolve somewhere
# else, so /app/backend, /app/frontend/dist, /app/runtime and /app/customers
# are all load-bearing paths, not conventions.
#
# What this image does NOT contain: customers/ (live Tradier tokens) and var/
# (the SQLite ledger). Both are excluded by .dockerignore. Credentials arrive
# as Secret Manager files mounted at runtime and the ledger lives in Postgres.

# ---------------------------------------------------------------- frontend
FROM node:24-slim AS web
WORKDIR /build

# package files first so a source-only edit reuses the install layer
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
# No VITE_TRADIER_API: the API serves this bundle from its own origin, so
# apiBase() resolving to same-origin is exactly right. Baking a URL here
# would send the browser somewhere else.
RUN npm run build


# ----------------------------------------------------------------- runtime
# 3.13 rather than the 3.14 used locally: pyproject asks for >=3.12, and 3.13
# is where numpy/pandas/lxml all have wheels. A source build of those on
# -slim needs a toolchain and several minutes per deploy.
FROM python:3.13-slim AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# curl for the healthcheck; tzdata because the trading day is defined in
# Central and the EOD auto-close compares against a CST wall clock.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

COPY backend/ ./backend/
COPY runtime/ ./runtime/
COPY worlds.json ./worlds.json
COPY --from=web /build/dist ./frontend/dist

# customers/ is mounted from Secret Manager at runtime; the directory has to
# exist first or the mount has nowhere to land. var/ is created because
# log_dir still wants a home even on Postgres.
RUN mkdir -p /app/customers /app/var

# Cloud Run injects PORT and routes to it. Binding a fixed port here would
# make the container start and then fail its readiness check.
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

WORKDIR /app/backend
# One worker, deliberately. Every worker would run its own copy of the
# background monitor loop, and two loops on one holding is the doubled-sell
# this app already warns about at startup. Concurrency is handled by async,
# not by processes.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --workers 1 --timeout-keep-alive 15
