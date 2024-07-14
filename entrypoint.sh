#!/usr/bin/fish
set PUID (set -q PUID; and echo $PUID; or echo 1000)
set PGID (set -q PGID; and echo $PGID; or echo 1000)

echo "Starting Container with $PUID:$PGID permissions..."

if [ "$PUID" = "0" ] 
    echo running as root user
    set USER_HOME "/home/$USERNAME"
    mkdir -p $USER_HOME
else
    if not echo $PUID | grep -qE '^[0-9]+$'
        echo "PUID is not a valid integer. Exiting..."
        exit 1
    end
    
    if not echo $PGID | grep -qE '^[0-9]+$'
        echo "PGID is not a valid integer. Exiting..."
        exit 1
    end
    
    set -q USERNAME; or set USERNAME riven
    set -q GROUPNAME; or set GROUPNAME riven
    
    if not getent group $PGID > /dev/null
        addgroup -g $PGID $GROUPNAME
        if test $status -ne 0
    	echo "Failed to create group. Exiting..."
    	exit 1
        end
    else
        set GROUPNAME (getent group $PGID | cut -d: -f1)
    end
    
    if not getent passwd $USERNAME > /dev/null
        adduser -D -u $PUID -G $GROUPNAME $USERNAME
        if test $status -ne 0
    	echo "Failed to create user. Exiting..."
    	exit 1
        end
    else
        if test $PUID -ne 0
    	usermod -u $PUID -g $PGID $USERNAME
    	if test $status -ne 0
    	    echo "Failed to modify user UID/GID. Exiting..."
    	    exit 1
    	end
        else
    	echo "Skipping usermod for root user."
        end
    end
    
    set USER_HOME "/home/$USERNAME"
    mkdir -p $USER_HOME
    chown -R $PUID:$PGID $USER_HOME
    chown -R $PUID:$PGID /riven/data
end

umask 002

set -x XDG_CONFIG_HOME "$USER_HOME/.config"
set -x XDG_DATA_HOME "$USER_HOME/.local/share"
set -x POETRY_CACHE_DIR "$USER_HOME/.cache/pypoetry"
set -x HOME $USER_HOME

# Ensure poetry is in the PATH
set -x PATH $PATH /app/.venv/bin

su -m $USERNAME -c "poetry config virtualenvs.create false"
set -q ORIGIN; or set ORIGIN "http://localhost:3000"
set -q BACKEND_URL; or set BACKEND_URL "http://127.0.0.1:8080"

echo "Container Initialization complete."

# Start rclone in the background
# echo "Starting rclone..."
# rclone rcd --rc-web-gui --rc-addr 0.0.0.0:5572 --rc-no-auth --log-level ERROR &> /dev/null &
# set rclone_pid (jobs -p %1)

# Start the backend
echo "Starting backend..."
su -m $USERNAME -c "fish -c 'cd /riven/backend; and poetry run python3 main.py'" &
set backend_pid (jobs -p %1)

# Start the frontend
echo "Starting frontend..."
exec su -m $USERNAME -c "fish -c 'ORIGIN=$ORIGIN BACKEND_URL=$BACKEND_URL node /riven/frontend/build'"
