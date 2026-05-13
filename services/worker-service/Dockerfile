# Dockerfile — builds the worker-service container image.
#
# Follows the same pattern as api-service/Dockerfile for consistency:
#   - python:3.11-slim base keeps the image small.
#   - Dependencies installed before application code to exploit Docker's layer
#     cache: a code-only change does not re-run pip install.
#   - Non-root appuser satisfies the principle of least privilege.
#   - Gunicorn as the production WSGI server; exec-form CMD for clean SIGTERM.

# ---------------------------------------------------------------------------
# Base image
# ---------------------------------------------------------------------------
FROM python:3.11-slim

# ---------------------------------------------------------------------------
# System-level setup
# ---------------------------------------------------------------------------
# Create a dedicated system user and group with no login shell.
# Running as a non-root user limits blast radius if the container is
# compromised — the attacker cannot write to system paths or install packages.
RUN groupadd --system appuser && useradd --system --gid appuser appuser

# ---------------------------------------------------------------------------
# Working directory
# ---------------------------------------------------------------------------
# All COPY / RUN / CMD paths are relative to /app from this point on.
WORKDIR /app

# ---------------------------------------------------------------------------
# Layer-cached dependency installation
# ---------------------------------------------------------------------------
# Copy requirements.txt first so Docker can cache the pip install layer.
# If only app.py changes on the next build, this layer is served from cache
# and the (potentially slow) network download is skipped entirely.
COPY requirements.txt .

# --no-cache-dir prevents pip from writing its HTTP cache into the image layer,
# saving ~10-20 MB for nothing (the cache is discarded after each build anyway).
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Application code
# ---------------------------------------------------------------------------
# Copied after deps so that iterative code edits do not bust the cache above.
COPY app.py .

# ---------------------------------------------------------------------------
# Ownership handoff
# ---------------------------------------------------------------------------
# Give appuser ownership of /app so it can write any runtime temp files.
# This must happen while still root (before the USER instruction below).
RUN chown -R appuser:appuser /app

# All subsequent instructions and the final container process run as appuser.
USER appuser

# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------
# Documents the port the application listens on.  Does not publish the port —
# that is handled by the Kubernetes Service or `docker run -p`.
EXPOSE 8080

# ---------------------------------------------------------------------------
# Start command
# ---------------------------------------------------------------------------
# Gunicorn is a production WSGI server.  Differences from Flask's dev server:
#   - Multi-process: --workers 2 handles concurrent requests without threading.
#   - No auto-reload, no PIN debugger, no debug tracebacks exposed to clients.
#   - Graceful shutdown: exec-form CMD means the kernel sends SIGTERM directly
#     to the gunicorn master process, which drains in-flight requests before
#     exiting — important for zero-downtime rolling deploys in Kubernetes.
#
# --workers 2  : conservative for a pod with 0.25–0.5 CPU limits; scale up if
#                profiling shows the workers are CPU-bound.
# app:app      : module "app" (app.py), Flask object named "app".
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:8080", "app:app"]
