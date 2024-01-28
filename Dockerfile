# Frontend Builder
FROM node:20-alpine AS frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install esbuild@0.19.9
RUN npm install
COPY frontend/ .
RUN npm run build && npm prune --production

# Final Image
FROM node:20-alpine

LABEL name="Iceberg" \
      description="Iceberg Debrid Downloader" \
      url="https://github.com/dreulavelle/iceberg"

RUN apk --update add --no-cache python3 py3-pip tzdata bash shadow && \
    rm -rf /var/cache/apk/*

WORKDIR /iceberg

ARG ORIGIN
ARG RD_API_KEY
ARG PLEX_URL
ARG PLEX_TOKEN

ARG JACKETT_URL
ARG JACKETT_API_KEY

ENV ORIGIN=${ORIGIN:-http://localhost:3000}
ENV TZ=${TZ:-America/New_York}

EXPOSE 3000 8080

# Frontend
COPY --from=frontend --chown=node:node /app/build /iceberg/frontend/build
COPY --from=frontend --chown=node:node /app/node_modules /iceberg/frontend/node_modules
COPY --from=frontend --chown=node:node /app/package.json /iceberg/frontend/package.json

# Backend
COPY backend/ /iceberg/backend
RUN python3 -m venv /venv
COPY requirements.txt /iceberg/requirements.txt
RUN source /venv/bin/activate && pip install -r /iceberg/requirements.txt

COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["/iceberg/entrypoint.sh"]
