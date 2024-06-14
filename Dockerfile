# Iceberg Backend Builder

FROM python:3.11-alpine
LABEL name="Iceberg" \
      description="Iceberg Debrid Downloader" \
      url="https://github.com/dreulavelle/iceberg"

# Install system dependencies
RUN apk --update add --no-cache curl bash shadow && \
    rm -rf /var/cache/apk/*
RUN pip install --upgrade pip && pip install poetry==1.8.3

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Install Poetry globally
ENV POETRY_HOME="/etc/poetry"
ENV PATH="$POETRY_HOME/bin:$PATH"
#RUN curl -sSL https://install.python-poetry.org | python3 - --yes

# Setup the application directory
WORKDIR /iceberg

# Expose ports
EXPOSE 8080

# Set environment variable to force color output
ENV FORCE_COLOR=1
ENV TERM=xterm-256color

# Copy the Python project files
COPY pyproject.toml poetry.lock* /iceberg/

# Install Python dependencies
RUN poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR 
RUN poetry add pydantic-settings

# Copy backend code and other necessary files
COPY backend/ /iceberg/backend
COPY VERSION entrypoint.sh /iceberg/

# Ensure entrypoint script is executable
RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["/bin/sh", "-c", "/iceberg/entrypoint.sh"]