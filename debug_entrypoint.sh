#!/bin/bash
: ${PUID:=1000}
: ${PGID:=1000}

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

USER_HOME="/home/${USERNAME}"
mkdir -p ${USER_HOME}
chown ${USERNAME}:${GROUPNAME} ${USER_HOME}
chown -R ${USERNAME}:${GROUPNAME} /iceberg
export XDG_CONFIG_HOME="${USER_HOME}/.config"
export POETRY_CACHE_DIR="${USER_HOME}/.cache/pypoetry"
su -m $USERNAME -c "poetry config virtualenvs.create false"
ORIGIN=${ORIGIN:-http://localhost:3000}

echo "Container Initialization complete."
exec su -m $USERNAME -c "cd /iceberg/backend && poetry run python3 -m debugpy --listen 0.0.0.0:5678 --wait-for-client main.py"