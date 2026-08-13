"""Gunicorn configuration.

A file rather than a wall of command-line flags, so the tuning is reviewable
and every environment gets the same defaults. Anything worth changing per host
reads from the environment.
"""

from __future__ import annotations

import multiprocessing
import os

# ---------------------------------------------------------------------------
# Socket
# ---------------------------------------------------------------------------

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# Connections the kernel will queue before refusing. Absorbs a traffic spike
# for the second or two it takes workers to catch up.
backlog = 2048

# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------
# (2 x cores) + 1 is the standard starting point for a request/response app.
# This one is IO-bound — Postgres, Redis, the payment gateway — so workers
# spend most of their life blocked and oversubscribing cores is the point.
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))

# Sync workers, deliberately. Gevent would raise per-worker concurrency, but
# psycopg2 is not green-thread friendly without extra patching, and a
# monkey-patched database driver is not something to debug at 3am for
# throughput this app does not yet need.
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "sync")

# Threads per worker. Cheap concurrency for the IO wait, without the
# monkey-patching. Ignored by the sync worker unless > 1, which promotes it to
# the threaded worker.
threads = int(os.environ.get("GUNICORN_THREADS", 2))

# Kill a request that hangs. Longer than any real endpoint: the slowest is an
# invoice PDF or a CSV export of five thousand orders.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 60))

# How long a worker gets to finish in-flight requests during a reload.
graceful_timeout = 30

# Nginx holds connections open; matching that avoids a connection being torn
# down mid-keepalive. Must stay below the proxy's own idle timeout.
keepalive = 5

# ---------------------------------------------------------------------------
# Worker recycling
# ---------------------------------------------------------------------------
# Long-lived Django processes accumulate memory — cached querysets, connection
# state, third-party leaks. Recycling caps the damage without anyone noticing.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", 1000))

# Jitter, so all workers do not recycle on the same request and drop capacity
# to zero at the same moment.
max_requests_jitter = 100

# ---------------------------------------------------------------------------
# Application loading
# ---------------------------------------------------------------------------
# Import the app once in the master and fork. Saves memory through
# copy-on-write and moves import errors to boot, where they crash the container
# instead of every request.
#
# The cost: a forked worker inherits the master's database connections, so
# nothing may connect at import time. This project does not.
preload_app = True

wsgi_app = "config.wsgi:application"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# Both streams to stdout/stderr: the container runtime is the log collector.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Adds request time (%(D)s, microseconds) and the request id the application's
# own middleware issues, so a slow request can be traced from the proxy log
# into the application log.
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s "%({x-request-id}o)s"'
)

# Health checks are the majority of access-log volume and carry no information.
def _is_probe(environ: dict) -> bool:
    """Return whether a request is a load-balancer probe."""
    return environ.get("PATH_INFO", "") in {"/health/", "/ready/"}


# ---------------------------------------------------------------------------
# Process naming
# ---------------------------------------------------------------------------

proc_name = "fashion-trendz"


def on_starting(server: object) -> None:
    """Log the configuration once, at boot."""
    server.log.info(  # type: ignore[attr-defined]
        "starting fashion-trendz: %s worker(s), %s thread(s), %ss timeout",
        workers,
        threads,
        timeout,
    )


def worker_abort(worker: object) -> None:
    """Log which worker was killed by the timeout.

    Without this, a hung request produces an anonymous "WORKER TIMEOUT" and no
    indication of what it was doing.
    """
    worker.log.error("worker %s aborted (timeout)", worker.pid)  # type: ignore[attr-defined]
