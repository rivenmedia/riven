# Frontend Builder
FROM node:20-alpine AS frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build && npm prune --production

# Final Image
FROM node:20-alpine
LABEL name="Iceberg" \
      description="Iceberg Debrid Downloader" \
      url="https://github.com/dreulavelle/iceberg"

# Install system dependencies
RUN apk --update add --no-cache python3 curl bash shadow && \
    rm -rf /var/cache/apk/* 

# Install Poetry globally
ENV POETRY_HOME="/etc/poetry"
ENV PATH="$POETRY_HOME/bin:$PATH"
RUN curl -sSL https://install.python-poetry.org | python3 - --yes

# Setup the application directory
WORKDIR /iceberg

# Expose ports
EXPOSE 3000 8080

# Copy frontend build from the previous stage
COPY --from=frontend --chown=node:node /app/build /iceberg/frontend/build
COPY --from=frontend --chown=node:node /app/node_modules /iceberg/frontend/node_modules
COPY --from=frontend --chown=node:node /app/package.json /iceberg/frontend/package.json

# Copy the Python project files
COPY pyproject.toml poetry.lock* /iceberg/

# Install Python dependencies
RUN poetry config virtualenvs.create false && \
    poetry install --no-dev

# Copy backend code and other necessary files
COPY backend/ /iceberg/backend
COPY VERSION entrypoint.sh /iceberg/

# Ensure entrypoint script is executable
RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["/iceberg/entrypoint.sh"]
