# Fashion Trendz API.
#
# Multi-stage: wheels are built in a stage with a compiler, then copied into a
# runtime image that has none. That keeps gcc and the Postgres headers out of
# the shipped image — smaller, and one less thing an attacker who gets a shell
# can use.

# ---------------------------------------------------------------------------
# Stage 1 — build wheels
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Build-only dependencies: psycopg2 and Pillow both compile against system
# libraries.
RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
        libpq-dev \
        libjpeg-dev \
        zlib1g-dev \
        libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings

# Runtime libraries only — the shared objects the wheels link against, not the
# headers they were compiled with.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libpq5 \
        libjpeg62-turbo \
        zlib1g \
        libfreetype6 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user. A container that runs as root turns a code-execution
# bug into a container-escape attempt.
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home app

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* && rm -rf /wheels

COPY --chown=app:app . .

# Static files are collected at build time, not at boot: it is deterministic,
# it fails the build rather than the deploy, and every replica ships identical
# hashed filenames.
RUN SECRET_KEY=build-only DEBUG=False \
    DB_NAME=x DB_USER=x DB_PASSWORD=x \
    python manage.py collectstatic --noinput --clear

RUN mkdir -p /app/media /app/logs && chown -R app:app /app/media /app/logs

USER app

EXPOSE 8000

# Uses the application's own readiness endpoint, so the container is only
# healthy when its database and cache are reachable — not merely when the
# process has started.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/ready/ || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "gunicorn.conf.py"]
