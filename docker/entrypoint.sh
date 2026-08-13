#!/usr/bin/env bash
# Container entrypoint.
#
# Waits for the database, applies migrations, then hands control to whatever
# command the container was given — web, worker or beat all share this image
# and therefore this script.
set -euo pipefail

log() { echo "[entrypoint] $*"; }

# ---------------------------------------------------------------------------
# Wait for Postgres
# ---------------------------------------------------------------------------
# Compose's depends_on only waits for the container to start, not for Postgres
# to accept connections. Without this, the first deploy of a stack races and
# the web container exits before the database is listening.
wait_for_database() {
  local attempts=${DB_WAIT_ATTEMPTS:-30}

  for ((i = 1; i <= attempts; i++)); do
    if python - <<'PY' 2>/dev/null
import os, sys
import psycopg2

try:
    psycopg2.connect(
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        connect_timeout=3,
    ).close()
except Exception:
    sys.exit(1)
PY
    then
      log "database is accepting connections"
      return 0
    fi
    log "waiting for database ($i/$attempts)"
    sleep 2
  done

  log "database did not become available"
  return 1
}

wait_for_database

# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
# Only the web container migrates. Workers and beat share this entrypoint, and
# three replicas racing to apply the same migration is how a deploy deadlocks
# on a table lock.
if [[ "${RUN_MIGRATIONS:-true}" == "true" && "${1:-}" == "gunicorn" ]]; then
  log "applying migrations"
  python manage.py migrate --noinput
fi

log "starting: $*"
exec "$@"
