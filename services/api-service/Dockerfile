# Dockerfile — builds the api-service container image.
#
# Design decisions:
#   - python:3.11-slim keeps the image small (~60 MB base) while still shipping
#     a full CPython interpreter.  "slim" omits docs, tests, and some dev tools
#     that are not needed at runtime.
#   - Dependencies are installed BEFORE copying application code so that Docker's
#     layer cache can skip the (slow) pip install step on rebuilds where only
#     source files changed.
#   - The app runs as a non-root user (appuser) to follow the principle of least
#     privilege.  If the container is compromised, the attacker cannot write to
#     system paths or install system packages.

# ---------------------------------------------------------------------------
# Base image
# ---------------------------------------------------------------------------
FROM python:3.11-slim

# ---------------------------------------------------------------------------
# System-level setup
# ---------------------------------------------------------------------------
# Create a dedicated non-root user and group.
# --system       : no login shell, no home dir entry in /etc/passwd (cleaner)
# --group        : also create a matching group with the same name
# Using a named user (rather than a numeric UID only) makes `docker exec` and
# log output more readable.
RUN groupadd --system appuser && useradd --system --gid appuser appuser

# ---------------------------------------------------------------------------
# Working directory
# ---------------------------------------------------------------------------
# All subsequent COPY / RUN / CMD instructions operate relative to this path.
# Creating it explicitly (rather than relying on COPY to create it) makes the
# intent clear and ensures correct ownership when we chown below.
WORKDIR /app

# ---------------------------------------------------------------------------
# Layer-cached dependency installation
# ---------------------------------------------------------------------------
# Copy ONLY the requirements file first.  Docker caches each layer keyed on the
# files copied into it.  As long as requirements.txt is unchanged, this layer
# (and the pip install below) are served from cache — even when app.py changes.
COPY requirements.txt .

# --no-cache-dir  : do not write the pip HTTP cache to disk (saves ~20 MB in
#                   the image layer for nothing — the cache is never reused
#                   across image builds).
# --upgrade pip   : ensures we are not blocked by a pip bug fixed in a newer
#                   release; runs before the install to keep the two concerns
#                   in a single RUN layer.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Application code
# ---------------------------------------------------------------------------
# Copied after deps so that code edits do not bust the requirements cache layer.
COPY app.py .

# ---------------------------------------------------------------------------
# Ownership handoff
# ---------------------------------------------------------------------------
# Recursively set ownership of /app to appuser so the process can write log
# files or temp files to its own working directory if needed.
RUN chown -R appuser:appuser /app

# Switch to the non-root user for all subsequent instructions and at runtime.
USER appuser

# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------
# Document that the application listens on 8080.  EXPOSE does not actually
# publish the port — that is done in docker run / Kubernetes Service / Compose —
# but it serves as machine-readable documentation and is used by some tooling.
EXPOSE 8080

# ---------------------------------------------------------------------------
# Start command
# ---------------------------------------------------------------------------
# Use Gunicorn (a production-grade WSGI server) instead of Flask's built-in
# dev server.  The dev server is single-threaded and prints a warning when used
# in production.
#
# Flags:
#   --workers 2        : 2 worker processes handle requests concurrently.
#                        Rule of thumb: 2 * CPU_cores + 1; 2 is safe for a
#                        pod with 0.25–0.5 CPU limits.
#   --bind 0.0.0.0:8080: listen on all interfaces inside the container so
#                        Kubernetes can route traffic to the pod.
#   app:app            : module "app" (app.py), Flask object named "app".
#
# Using the exec form (JSON array) rather than shell form means the process
# receives SIGTERM directly from the kernel — enabling graceful shutdown —
# instead of being wrapped in /bin/sh which would swallow the signal.
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:8080", "app:app"]
