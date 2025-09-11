# Builder Image for Python Dependencies
FROM python:3.11-alpine AS builder

# Install necessary build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    python3-dev \
    build-base \
    curl \
    curl-dev \
    openssl-dev \
    fuse3-dev \
    pkgconf \
    fuse3

# Upgrade pip and install poetry
ENV PYCURL_SSL_LIBRARY=openssl
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
    libcurl \
    openssl \
    shadow \
    rclone \
    unzip \
    gcc \
    ffmpeg \
    musl-dev \
    libffi-dev \
    python3-dev \
    libpq-dev \
    fuse3

# Ensure FUSE allows allow_other (uncomment or add user_allow_other)
RUN (sed -i 's/^#\s*user_allow_other/user_allow_other/' /etc/fuse.conf 2>/dev/null || true) \
    && (grep -q '^user_allow_other' /etc/fuse.conf 2>/dev/null || echo 'user_allow_other' >> /etc/fuse.conf)


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
