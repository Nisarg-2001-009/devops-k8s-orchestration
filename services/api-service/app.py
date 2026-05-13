# app.py — Entry point for the api-service Flask application.
# This service acts as the front-facing API gateway in the Kubernetes cluster.
# It exposes health check endpoints (used by Kubernetes liveness/readiness probes)
# and API endpoints that demonstrate inter-service communication patterns.

import os
from datetime import datetime, timezone

from flask import Flask, jsonify

# ---------------------------------------------------------------------------
# App initialisation
# ---------------------------------------------------------------------------
# Flask uses __name__ to locate resources relative to this file.
app = Flask(__name__)


# ---------------------------------------------------------------------------
# Root route
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    """Simple welcome message — useful for a quick smoke-test."""
    return jsonify({
        "message": "Welcome to api-service",
        "docs": "/api/info",
    })


# ---------------------------------------------------------------------------
# Kubernetes liveness probe
# ---------------------------------------------------------------------------
# Kubernetes calls /health/live to decide whether to *restart* the container.
# It should return 200 as long as the process is running and not deadlocked.
# Deliberately kept lightweight — no external calls, no DB checks.
@app.route("/health/live", methods=["GET"])
def liveness():
    return jsonify({
        "status": "alive",
        "service": "api-service",
    })


# ---------------------------------------------------------------------------
# Kubernetes readiness probe
# ---------------------------------------------------------------------------
# Kubernetes calls /health/ready to decide whether to *send traffic* to the
# pod. A timestamp is included so ops can confirm the check is live and not
# being served from a cache.
@app.route("/health/ready", methods=["GET"])
def readiness():
    return jsonify({
        "status": "ready",
        "service": "api-service",
        # datetime.now(timezone.utc) is the modern, non-deprecated way to get
        # a timezone-aware UTC timestamp; .isoformat() gives RFC-3339 format.
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Service info
# ---------------------------------------------------------------------------
# Returns static metadata about this service.  APP_ENV is injected via a
# Kubernetes ConfigMap or a local .env file so the same image can run in
# dev / staging / production without rebuilding.
@app.route("/api/info", methods=["GET"])
def info():
    return jsonify({
        "service": "api-service",
        "version": "1.0.0",
        # os.getenv(key, default) is preferred over os.environ[key] because it
        # never raises KeyError — safe even when the var is not set.
        "environment": os.getenv("APP_ENV", "development"),
    })


# ---------------------------------------------------------------------------
# Process endpoint
# ---------------------------------------------------------------------------
# Demonstrates how this service would delegate work to the worker-service.
# WORKER_SERVICE_URL is resolved by Kubernetes DNS when deployed in-cluster
# (the default "http://worker-service:8080" matches the Service name defined
# in k8s/worker-service.yaml). Override it locally to point at a local port.
@app.route("/api/process", methods=["GET"])
def process():
    worker_url = os.getenv("WORKER_SERVICE_URL", "http://worker-service:8080")
    return jsonify({
        "status": "processed",
        "message": "Task handled by api-service",
        "worker_url": worker_url,
    })


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------
# This block is only executed when running `python app.py` directly (e.g.
# during local development).  In production / Docker, Gunicorn (or another
# WSGI server) imports the `app` object directly and this block is skipped.
if __name__ == "__main__":
    # host="0.0.0.0" makes the dev server reachable from outside the container.
    # debug=True enables the Werkzeug reloader and detailed tracebacks — never
    # set this in production.
    app.run(host="0.0.0.0", port=8080, debug=True)
