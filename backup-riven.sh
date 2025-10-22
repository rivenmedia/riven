#!/bin/bash
# backup-riven.sh — Riven + Postgres backup script

set -euo pipefail
umask 077

BACKUP_DIR="/path/to/backups" # Change this to your desired backup directory
DATE="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

RIVEN_CONTAINER="riven" # Change this to your Riven app container name
RIVEN_DB_CONTAINER="riven-db" # Change this to your Riven DB container name
RIVEN_DATA="./riven/data" # Change this to your Riven data directory

echo "[1/5] Stopping app container ($RIVEN_CONTAINER)…"
docker stop "$RIVEN_CONTAINER" || true

echo "[2/5] Ensuring DB container ($RIVEN_DB_CONTAINER) is running..."
if ! docker ps --format '{{.Names}}' | grep -q "^$RIVEN_DB_CONTAINER$"; then
  docker start "$RIVEN_DB_CONTAINER"
fi

echo "      Waiting for Postgres to be ready..."
for i in {1..30}; do
  if docker exec "$RIVEN_DB_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "[3/5] Dumping database..."
docker exec -e PGPASSWORD=postgres "$RIVEN_DB_CONTAINER" \
  pg_dump -U postgres -d riven -Fc > "$BACKUP_DIR/riven-db-$DATE.dump"
echo "      ✓ Database dump saved to $BACKUP_DIR/riven-db-$DATE.dump"

echo "[4/5] Archiving app data..."
if [[ -d "$RIVEN_DATA" ]]; then
  tar czf "$BACKUP_DIR/riven-data-$DATE.tar.gz" -C "$RIVEN_DATA" .
  echo "      ✓ Data archived to $BACKUP_DIR/riven-data-$DATE.tar.gz"
else
  echo "      ✗ Not found: $RIVEN_DATA"
fi

echo "[5/5] Restarting app container..."
docker start "$RIVEN_CONTAINER" || true

echo "      Cleaning backups older than 7 days..."
find "$BACKUP_DIR" -type f -mtime +7 \
  \( -name 'riven-db-*.dump' -o -name 'riven-data-*.tar.gz' \) -delete

echo "✅ Done. Backups stored in: $BACKUP_DIR"
