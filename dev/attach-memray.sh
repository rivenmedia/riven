#!/bin/bash
# Attach memray to the running main.py process
# Usage: ./attach-memray.sh

pgrep -f "main.py" | head -n 2 | xargs -I{} memray attach {}