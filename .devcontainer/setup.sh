# Check if credentials file exists
if [ ! -f /workspace/dev/mount/credentials ]; then
    clear
    echo "================================================================"
    echo "                  RCLONE SETUP REQUIRED"
    echo "================================================================"
    echo "No credentials found. Please enter your Real-Debrid credentials."
    echo "----------------------------------------------------------------"

    # Prompt for credentials
    echo -n "Enter token: "
    read -r TOKEN
    echo -n "Enter WEBDAV pass:"
    read -r PASS
    echo  # New line after password input

    # Store credentials
    cat > /workspace/dev/mount/credentials << EOF
TOKEN=$TOKEN
PASS=$PASS
EOF

    chmod 600 /workspace/dev/mount/credentials
    echo "Credentials saved successfully!"
    echo "================================================================"
fi