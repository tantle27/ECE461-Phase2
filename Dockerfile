# syntax=docker/dockerfile:1.7

# ---- Base image ----
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps (git for git metrics, build deps for some wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Python deps ----
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---- App code ----
COPY . .

# Expose Flask port
EXPOSE 80

# Default command: gunicorn serving the Flask app instance from registry.py
# GUNICORN_CMD_ARGS lets you tune workers via env (e.g., GUNICORN_CMD_ARGS="-w 2 -k gthread")
ENV GUNICORN_CMD_ARGS="-w 2 --threads 2 --timeout 120"
CMD ["gunicorn", "--factory", "-b", "0.0.0.0:80", "app.core:create_app"]