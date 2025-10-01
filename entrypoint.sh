#!/bin/sh

# Default PUID and PGID to 1000 if not set
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Starting Container with $PUID:$PGID permissions..."

if [ "$PUID" = "0" ]; then
    echo "Running as root user"
    USER_HOME="/root"
else
    # --- User and Group Management ---
    USERNAME=${USERNAME:-riven}
    GROUPNAME=${GROUPNAME:-riven}
    USER_HOME="/home/$USERNAME"
    if ! getent group "$PGID" > /dev/null; then addgroup --gid "$PGID" "$GROUPNAME"; fi
    GROUPNAME=$(getent group "$PGID" | cut -d: -f1)
    if ! getent passwd "$USERNAME" > /dev/null; then adduser -D -h "$USER_HOME" -u "$PUID" -G "$GROUPNAME" "$USERNAME"; fi
    usermod -u "$PUID" -g "$PGID" "$USERNAME"
    adduser "$USERNAME" wheel
fi

# Set home directory permissions and environment
mkdir -p "$USER_HOME"
chown -R "$PUID:$PGID" "$USER_HOME"
export HOME="$USER_HOME"

# Define the command to run based on the DEBUG flag
if [ "${DEBUG}" != "" ]; then
    echo "Installing debugpy..."
    pip install debugpy
    CMD="/riven/.venv/bin/python -m debugpy --listen 0.0.0.0:5678 src/main.py"
else
    CMD="/riven/.venv/bin/python src/main.py"
fi


echo "Container Initialization complete."
echo "Starting Riven (Backend)..."

# Execute the command
if [ "$PUID" = "0" ]; then
    exec $CMD
else
    exec su -m "$USERNAME" -c "$CMD"
fi