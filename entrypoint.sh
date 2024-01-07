#!/bin/bash

echo "Starting Container with ${PUID:-1000}:${PGID:-1000} permissions..."

if ! [ "$PUID" -eq "$PUID" ] 2> /dev/null; then
    echo "PUID is not a valid integer. Exiting..."
    exit 1
fi

if ! [ "$PGID" -eq "$PGID" ] 2> /dev/null; then
    echo "PGID is not a valid integer. Exiting..."
    exit 1
fi

: ${USERNAME:=iceberg}
: ${GROUPNAME:=iceberg}

if ! getent group ${PGID} >/dev/null; then
    addgroup -g $PGID $GROUPNAME > /dev/null
else
    GROUPNAME=$(getent group ${PGID} | cut -d: -f1)
fi

if ! getent passwd ${PUID} >/dev/null; then
    adduser -D -u $PUID -G $GROUPNAME $USERNAME > /dev/null
else
    USERNAME=$(getent passwd ${PUID} | cut -d: -f1)
fi

chown -R ${USERNAME}:${GROUPNAME} /iceberg

ORIGIN=${ORIGIN:-http://localhost:3000}

echo "Container Initialization complete."
exec su -m $USERNAME -c 'cd backend && source /venv/bin/activate && exec python /iceberg/backend/main.py & ORIGIN=$ORIGIN node /iceberg/frontend/build'
