# -----------------
# Builder Stage
# -----------------
FROM python:3.11-alpine AS builder

# Install only the necessary build dependencies
RUN apk add --no-cache gcc musl-dev libffi-dev python3-dev build-base curl curl-dev openssl-dev fuse3-dev pkgconf fuse3

# Install and configure poetry
RUN pip install --upgrade pip && pip install poetry==1.8.3
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

# Install dependencies
COPY pyproject.toml poetry.lock ./
RUN poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR

# -----------------
# Final Stage
# -----------------
FROM python:3.11-alpine
LABEL name="Riven" \
      description="Riven Media Server" \
      url="https://github.com/rivenmedia/riven"

# Install only runtime dependencies
RUN apk add --no-cache curl libcurl shadow rclone unzip ffmpeg libpq fuse3 libcap libcap-utils

# Configure FUSE
RUN sed -i 's/^#\s*user_allow_other/user_allow_other/' /etc/fuse.conf || \
    echo 'user_allow_other' >> /etc/fuse.conf

WORKDIR /riven

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /riven/.venv

# Grant the necessary capabilities to the Python binary
RUN setcap cap_sys_admin+ep /usr/local/bin/python3.11

# Activate the virtual environment by adding it to the PATH
ENV PATH="/riven/.venv/bin:$PATH"

# Copy application code and entrypoint
COPY src/ ./src
COPY pyproject.toml poetry.lock ./
COPY entrypoint.sh ./

RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]