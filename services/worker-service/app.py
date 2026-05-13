# app.py — Entry point for the worker-service Flask application.
#
# worker-service is a background processing service in the Kubernetes cluster.
# It receives work payloads from api-service (or any other caller) via HTTP,
# processes them, and returns a structured result.  Keeping this logic in a
# separate service means it can be scaled, deployed, and restarted independently
# of the front-facing api-service.

import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# App initialisation
# ---------------------------------------------------------------------------
app = Flask(__name__)


# ---------------------------------------------------------------------------
# Root route
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    """Quick smoke-test endpoint — confirms the service is reachable."""
    return jsonify({
        "message": "Welcome to worker-service",
        "docs": "/api/info",
    })


# ---------------------------------------------------------------------------
# Kubernetes liveness probe
# ---------------------------------------------------------------------------
# Called by Kubernetes to decide whether to *restart* this container.
# Must be cheap: no I/O, no downstream calls.  Returns 200 as long as the
# Python process is alive and the event loop is not stuck.
@app.route("/health/live", methods=["GET"])
def liveness():
    return jsonify({
        "status": "alive",
        "service": "worker-service",
    })


# ---------------------------------------------------------------------------
# Kubernetes readiness probe
# ---------------------------------------------------------------------------
# Called by Kubernetes to decide whether to *route traffic* to this pod.
# The timestamp lets operators confirm the response is fresh (not cached by
# an intermediate proxy or load balancer).
@app.route("/health/ready", methods=["GET"])
def readiness():
    return jsonify({
        "status": "ready",
        "service": "worker-service",
        # timezone-aware UTC timestamp in RFC-3339 / ISO-8601 format.
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Service info
# ---------------------------------------------------------------------------
# Returns static metadata.  APP_ENV is injected via a Kubernetes ConfigMap
# (or a local .env file) so the same image runs unchanged across environments.
@app.route("/api/info", methods=["GET"])
def info():
    return jsonify({
        "service": "worker-service",
        "version": "1.0.0",
        "environment": os.getenv("APP_ENV", "development"),
    })


# ---------------------------------------------------------------------------
# Work endpoint
# ---------------------------------------------------------------------------
# Accepts a JSON payload from callers (typically api-service) and returns a
# structured result.  In a real system this route would enqueue a background
# job, call a database, or trigger a pipeline.  Here it echoes the payload
# back along with a server-side timestamp so the caller can verify round-trip
# latency and confirm the body arrived intact.
@app.route("/api/work", methods=["POST"])
def work():
    # request.get_json() parses the Content-Type: application/json body.
    # force=True also parses the body even if the Content-Type header is wrong
    # or missing — useful during local curl testing.
    # silent=True returns None instead of raising a 400 if the body is not
    # valid JSON, giving us a chance to handle the error ourselves.
    body = request.get_json(force=True, silent=True)

    # Reject requests that sent no body or an unparseable body so callers get
    # a clear error rather than a silent None in the "received" field.
    if body is None:
        return jsonify({
            "status": "error",
            "message": "Request body must be valid JSON",
        }), 400

    return jsonify({
        "status": "completed",
        "service": "worker-service",
        # Echo the received payload so the caller can confirm the body was
        # transmitted and deserialised correctly.
        "received": body,
        # Capture the server-side processing time so callers or tracing tools
        # can measure end-to-end latency by comparing this with their send time.
        "processed_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------
# Only executed when running `python app.py` directly (local dev).
# In Docker / Kubernetes, Gunicorn imports the `app` object and this block
# is skipped.  Never use debug=True in production — it enables code execution
# via the Werkzeug PIN debugger.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
