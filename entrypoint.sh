#!/bin/bash

# Display the UID and GID that will be used
echo "Starting Container with ${PUID:-1000}:${PGID:-1000} permissions..."

# Create or reuse group
if ! getent group "${PGID}" > /dev/null; then
    addgroup -g "${PGID}" iceberg
else
    existing_group=$(getent group "${PGID}" | cut -d: -f1) > /dev/null
    iceberg_group=$existing_group
fi

# Create or reuse user
if ! getent passwd "${PUID}" > /dev/null; then
    adduser -D -u "${PUID}" -G "${iceberg_group:-iceberg}" iceberg
else
    existing_user=$(getent passwd "${PUID}" | cut -d: -f1) > /dev/null
    iceberg_user=$existing_user
fi

chown -R "${PUID}:${PGID}" /iceberg
echo "Initialization complete. Executing main process..."
exec "$@"
