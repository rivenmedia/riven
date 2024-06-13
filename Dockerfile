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
LABEL name="Iceberg" \
      description="Iceberg Debrid Downloader" \
      url="https://github.com/dreulavelle/iceberg"

ARG S6_OVERLAY_VERSION=3.2.0.0
ARG TARGETPLATFORM=linux/amd64 # Set a default

# Install s6 noarch
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz

# Install arch-specific s6
RUN \ 
  case ${TARGETPLATFORM} in \
    "linux/amd64")  DOWNLOAD_ARCH="x86_64"  ;; \
    "linux/arm/v7") DOWNLOAD_ARCH="arm"  ;; \
  esac && \
  wget https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${DOWNLOAD_ARCH}.tar.xz -P /tmp \
  tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz \
  rm /tmp/s6-overlay-x86_64.tar.xz


# Install system dependencies and Node.js
ENV PYTHONUNBUFFERED=1
RUN apk add --no-cache \
    curl \
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

# Create user and group
RUN addgroup -g 1000 iceberg && \
    adduser -u 1000 -G iceberg -h /home/iceberg -s /usr/bin/fish -D iceberg

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

ENTRYPOINT ["/init"]