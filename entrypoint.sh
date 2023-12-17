#!/bin/sh

# Check and set default values for PUID and PGID if not provided
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Starting Container with $PUID:$PGID permissions..."

# Check if the iceberg user or group exists, and delete if they do
if getent passwd iceberg > /dev/null 2>&1; then
    deluser iceberg
fi
if getent group iceberg > /dev/null 2>&1; then
    delgroup iceberg
fi

# Create the iceberg group if it doesn't exist
if ! getent group $PGID > /dev/null 2>&1; then
    addgroup -g $PGID iceberg
else
    iceberg_group=$(getent group $PGID | cut -d: -f1)
    echo "Group with GID $PGID already exists as $iceberg_group"
fi

# Create the iceberg user
if ! getent passwd $PUID > /dev/null 2>&1; then
    adduser -D -u $PUID -G iceberg iceberg
else
    iceberg_user=$(getent passwd $PUID | cut -d: -f1)
    echo "User with UID $PUID already exists as $iceberg_user"
fi

chown -R iceberg:iceberg /iceberg
exec su iceberg -c "$@"
