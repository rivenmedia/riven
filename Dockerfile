# Builder Image for Python Dependencies
FROM python:3.11-slim AS builder
RUN apt-get update && apt-get install -y curl build-essential && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip && pip install poetry==1.4.2

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN touch README.md
RUN poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR

# Frontend Builder
FROM node:20-slim AS frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install -g pnpm && pnpm install
COPY frontend/ .
RUN pnpm run build && pnpm prune --prod

# Final Image
FROM python:3.11-slim
LABEL name="Iceberg" \
      description="Iceberg Debrid Downloader" \
      url="https://github.com/dreulavelle/iceberg"

# Install system dependencies and Node.js
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y \
    curl \
    fish \
    passwd \
    nodejs \
    npm \
    rclone && \
    npm install -g pnpm && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.4.2

# Create user and group
RUN groupadd -g 1000 iceberg && \
    useradd -u 1000 -g iceberg -m -s /usr/bin/fish iceberg

# Create fish config directory
RUN mkdir -p /home/iceberg/.config/fish

# Expose ports
EXPOSE 3000 8080 5572

# Set environment variable to force color output
ENV FORCE_COLOR=1
ENV TERM=xterm-256color

# Set working directory
WORKDIR /iceberg

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy the rest of the application code
COPY backend/ /iceberg/backend
COPY pyproject.toml poetry.lock /iceberg/backend/
COPY VERSION entrypoint.sh /iceberg/

# Copy frontend build from the previous stage
COPY --from=frontend --chown=iceberg:iceberg /app/build /iceberg/frontend/build
COPY --from=frontend --chown=iceberg:iceberg /app/node_modules /iceberg/frontend/node_modules
COPY --from=frontend --chown=iceberg:iceberg /app/package.json /iceberg/frontend/package.json

# Ensure entrypoint script is executable
RUN chmod +x /iceberg/entrypoint.sh

# Set correct permissions for the iceberg user
RUN chown -R iceberg:iceberg /home/iceberg/.config /iceberg

# Switch to fish shell
SHELL ["fish", "--login"]

ENTRYPOINT ["fish", "/iceberg/entrypoint.sh"]