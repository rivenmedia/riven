#!/bin/sh

echo "Starting Container with ${PUID}:${PGID} permissions..."

# Create group if it doesn't exist or reuse the existing group
if ! getent group $PGID > /dev/null; then
    addgroup -g $PGID iceberg
else
    existing_group=$(getent group $PGID | cut -d: -f1)
    echo "Group with GID $PGID already exists as $existing_group"
    iceberg_group=$existing_group
fi

# Create user if it doesn't exist or reuse the existing user
if ! getent passwd $PUID > /dev/null; then
    adduser -D -u $PUID -G ${iceberg_group:-iceberg} iceberg
else
    existing_user=$(getent passwd $PUID | cut -d: -f1)
    echo "User with UID $PUID already exists as $existing_user"
    iceberg_user=$existing_user
fi

# Change ownership of relevant directories
chown -R ${PUID}:${PGID} /iceberg

echo "Initialization complete. Executing main process..."
exec su -s /bin/sh -c "$@" ${iceberg_user:-iceberg}
