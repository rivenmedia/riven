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

# Frontend Builder
FROM node:20-alpine AS frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install -g pnpm && pnpm install
COPY frontend/ .
RUN pnpm run build && pnpm prune --prod

# Final Image
FROM python:3.11-alpine
LABEL name="Riven" \
      description="Riven Media Server" \
      url="https://github.com/rivenmedia/riven"

# Install system dependencies and Node.js
ENV PYTHONUNBUFFERED=1
RUN apk add --no-cache \
    curl \
    fish \
    shadow \
    nodejs \
    npm \
    rclone \
    fontconfig \
    unzip \
    gcc \
    musl-dev \
    libffi-dev \
    python3-dev && \
    npm install -g pnpm

# Install Nerd Fonts
RUN mkdir -p /usr/share/fonts/nerd-fonts && \
    curl -fLo "/usr/share/fonts/nerd-fonts/FiraCode.zip" \
    https://github.com/ryanoasis/nerd-fonts/releases/download/v2.1.0/FiraCode.zip && \
    unzip /usr/share/fonts/nerd-fonts/FiraCode.zip -d /usr/share/fonts/nerd-fonts && \
    rm /usr/share/fonts/nerd-fonts/FiraCode.zip && \
    fc-cache -fv

# Install Poetry
RUN pip install poetry==1.8.3

# Create fish config directory
RUN mkdir -p /home/riven/.config/fish

# Set environment variable to force color output
ENV FORCE_COLOR=1
ENV TERM=xterm-256color

# Set working directory
WORKDIR /riven

# Copy frontend build from the previous stage
COPY --from=frontend  /app/build /riven/frontend/build
COPY --from=frontend  /app/node_modules /riven/frontend/node_modules
COPY --from=frontend  /app/package.json /riven/frontend/package.json

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy the rest of the application code
COPY backend/ /riven/backend
COPY pyproject.toml poetry.lock /riven/backend/
COPY VERSION entrypoint.sh /riven/

# Ensure entrypoint script is executable
RUN chmod +x /riven/entrypoint.sh

# Switch to fish shell
SHELL ["fish", "--login"]

ENTRYPOINT ["fish", "/riven/entrypoint.sh"]
