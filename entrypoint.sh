#!/bin/sh

# Exit immediately if a command exits with a non-zero status
# set -e

# Treat unset variables as an error
# set -u

echo "Starting Iceberg container..."

# Check for required environment variables and validate configuration
# NOTE: This will be used to check for rclone flags and other configuration later
# required_vars=("REQUIRED_VAR1" "REQUIRED_VAR2")
# for var in "${required_vars[@]}"; do
#     if [ -z "${!var:-}" ]; then
#         echo "Error: Required environment variable '$var' not set."
#         exit 1
#     fi
# done

PUID=${PUID:-1000}
PGID=${PGID:-1000}

addgroup -g $PGID iceberg
adduser -D -u $PUID -G iceberg iceberg
chown -R 1000:1000 /iceberg
chmod -R 755 /iceberg

trap "echo 'Shutting down...'; exit" SIGINT SIGTERM
echo "Initialization complete. Executing main process..."
exec "$@"
