FROM alpine:3.19

LABEL org.label-schema.name="Iceberg" \
      org.label-schema.description="Iceberg Debrid Downloader" \
      org.label-schema.url="https://github.com/dreulavelle/iceberg"

# Define environment variables for PUID and PGID
ENV PUID=1000
ENV PGID=1000

# Install necessary packages
RUN apk --update add python3 py3-pip nodejs npm bash shadow vim nano rclone && \
    rm -rf /var/cache/apk/*

# Install pnpm
RUN npm install -g pnpm

# Set the working directory
WORKDIR /iceberg

# Copy the application files
COPY . /iceberg/

# Set up Python virtual environment and install dependencies
RUN python3 -m venv /venv && \
    source /venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt

# Build the frontend
RUN cd frontend && \
    pnpm install && \
    pnpm run build

# Create user and group for the application
RUN addgroup -g ${PGID} iceberg && \
    adduser -D -u ${PUID} -G iceberg iceberg && \
    chown -R iceberg:iceberg /iceberg

# Switch to the new user
USER iceberg

# Expose necessary ports
EXPOSE 4173 8080

# Start the backend first, then the frontend (suppressed frontend output)
CMD cd /iceberg/backend && source /venv/bin/activate && exec python main.py & \
    cd /iceberg/frontend && pnpm run preview --host 0.0.0.0 >/dev/null 2>&1