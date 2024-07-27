# Builder Image for Python Dependencies
FROM python:3.11-alpine AS builder

# Install necessary build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    python3-dev \
    build-base \
    curl

# Upgrade pip and install poetry
RUN pip install --upgrade pip && pip install poetry==1.8.3

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN touch README.md
RUN poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR

# Final Image
FROM python:3.11-alpine
LABEL name="Riven" \
      description="Riven Media Server" \
      url="https://github.com/rivenmedia/riven"

# Install system dependencies and Node.js
ENV PYTHONUNBUFFERED=1
RUN apk add --no-cache \
    curl \
    shadow \
    rclone \
    unzip \
    gcc \
    musl-dev \
    libffi-dev \
    python3-dev \
    libpq-dev \ 
    libtorrent

# Install Poetry
RUN pip install poetry==1.8.3

# Set environment variable to force color output
ENV FORCE_COLOR=1
ENV TERM=xterm-256color

# Set working directory
WORKDIR /riven

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy the rest of the application code
COPY src/ /riven/src
COPY pyproject.toml poetry.lock /riven/
COPY entrypoint.sh /riven/

# Ensure entrypoint script is executable
RUN chmod +x /riven/entrypoint.sh

ENTRYPOINT ["/riven/entrypoint.sh"]
