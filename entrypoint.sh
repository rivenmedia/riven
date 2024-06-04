#!/usr/bin/fish
set PUID (set -q PUID; and echo $PUID; or echo 1000)
set PGID (set -q PGID; and echo $PGID; or echo 1000)

echo "Starting Container with $PUID:$PGID permissions..."

if not echo $PUID | grep -qE '^[0-9]+$'
    echo "PUID is not a valid integer. Exiting..."
    exit 1
end

if not echo $PGID | grep -qE '^[0-9]+$'
    echo "PGID is not a valid integer. Exiting..."
    exit 1
end

set -q USERNAME; or set USERNAME iceberg
set -q GROUPNAME; or set GROUPNAME iceberg

if not getent group $PGID > /dev/null
    addgroup -g $PGID $GROUPNAME > /dev/null
else
    set GROUPNAME (getent group $PGID | cut -d: -f1)
end

if not getent passwd $PUID > /dev/null
    adduser -D -u $PUID -G $GROUPNAME $USERNAME > /dev/null
else
    set USERNAME (getent passwd $PUID | cut -d: -f1)
end

set USER_HOME "/home/$USERNAME"
mkdir -p $USER_HOME
chown $USERNAME:$GROUPNAME $USER_HOME
chown -R $USERNAME:$GROUPNAME /iceberg
set -x XDG_CONFIG_HOME "$USER_HOME/.config"
set -x XDG_DATA_HOME "$USER_HOME/.local/share"
set -x POETRY_CACHE_DIR "$USER_HOME/.cache/pypoetry"
set -x HOME $USER_HOME

# Ensure poetry is in the PATH
set -x PATH $PATH /app/.venv/bin

su -m $USERNAME -c "poetry config virtualenvs.create false"
set -q ORIGIN; or set ORIGIN "http://localhost:3000"

echo "Container Initialization complete."

# Start rclone in the background
# echo "Starting rclone..."
# rclone rcd --rc-web-gui --rc-addr 0.0.0.0:5572 --rc-no-auth --log-level ERROR &> /dev/null &
# set rclone_pid (jobs -p %1)

# Start the backend
echo "Starting backend..."
su -m $USERNAME -c "fish -c 'cd /iceberg/backend; and poetry run python3 main.py'" &
set backend_pid (jobs -p %1)

# Start the frontend
echo "Starting frontend..."
exec su -m $USERNAME -c "fish -c 'ORIGIN=$ORIGIN node /iceberg/frontend/build'"