FROM alpine:3.19

LABEL org.label-schema.name="Iceberg" \
      org.label-schema.description="Iceberg Debrid Downloader" \
      org.label-schema.url="https://github.com/dreulavelle/iceberg"

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

# Expose necessary ports
EXPOSE 4173 8080

# Copy and set permissions for the entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Set the entrypoint script
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Start the backend first, then the frontend (suppressed frontend output)
CMD cd backend && source /venv/bin/activate && exec python main.py & \
    cd frontend && pnpm run preview --host 0.0.0.0 >/dev/null 2>&1
