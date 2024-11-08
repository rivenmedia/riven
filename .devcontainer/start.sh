sudo umount /workspace/dev/mount/vfs
rm -fdr /workspace/dev/mount/vfs_cache

mkdir -p /workspace/dev/mount
mkdir -p /workspace/dev/mount/vfs

# Source credentials
if [ -f /workspace/dev/mount/credentials ]; then
    . /workspace/dev/mount/credentials
    echo "Starting rclone mount..."
    rclone mount \
    --allow-other \
    --allow-non-empty \
    --vfs-cache-mode minimal \
    --cache-dir /workspace/dev/mount/vfs_cache \
    --dir-cache-time 5s \
    :http: /workspace/dev/mount/vfs \
    --http-url "https://my.real-debrid.com/$PASS/torrents/" \
    --http-headers "Authorization,Bearer $TOKEN" \
    --http-no-head \
    --daemon

    #Wait a moment to check if mount succeeded
    sleep 2

    if mount | grep -q "/workspace/dev/mount/vfs"; then
        echo "Rclone mount started successfully"
        echo "VFS Mount point: /workspace/dev/mount/vfs"
        echo "Cache directory: /workspace/dev/mount/vfs_cache"

        chown vscode:vscode /workspace/dev/mount -R
    else
        exit 1
    fi
else
    echo "ERROR: Credentials file not found or setup failed!"
    exit 1
fi