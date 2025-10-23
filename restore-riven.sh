#!/bin/bash
# restore-riven.sh — interactive restore (DB only / data only / both)

set -euo pipefail
umask 077

BACKUP_DIR="/path/to/backups" # Change this to your desired backup directory
RIVEN_DATA="./riven/data" # Change this to your Riven data directory
RIVEN_CONTAINER="riven" # Change this to your Riven app container name
RIVEN_DB_CONTAINER="riven-db" # Change this to your Riven DB container name

# Colors
green="\e[32m"; yellow="\e[33m"; red="\e[31m"; bold="\e[1m"; reset="\e[0m"

echo -e "${bold}=== Riven Restore Utility ===${reset}\n"

# --- Choose what to restore ---
echo "What would you like to restore?"
options=(
  "Database only"
  "App data only (${RIVEN_DATA})"
  "ALL (Database + App data)"
  "Cancel"
)
select choice in "${options[@]}"; do
  case "$REPLY" in
    1) MODE="db"; break ;;
    2) MODE="data"; break ;;
    3) MODE="both"; break ;;
    4) echo "Aborted."; exit 0 ;;
    *) echo "Please choose 1-4." ;;
  esac
done
echo -e "→ Selected mode: ${yellow}$choice${reset}\n"

DB_DUMP=""
DATA_TAR=""

# --- If DB restore is involved, pick DB dump ---
if [[ "$MODE" == "db" || "$MODE" == "both" ]]; then
  mapfile -t DB_FILES < <(ls -1t "$BACKUP_DIR"/riven-db-*.dump 2>/dev/null || true)
  if [[ ${#DB_FILES[@]} -eq 0 ]]; then
    echo -e "${red}✗ No riven-db-*.dump files found in $BACKUP_DIR${reset}"
    exit 1
  fi
  echo "Available database backups:"
  select DB_DUMP in "${DB_FILES[@]}"; do
    [[ -n "${DB_DUMP:-}" ]] && break
  done
  echo -e "→ Selected DB dump: ${yellow}$(basename "$DB_DUMP")${reset}\n"
fi

# --- If data restore is involved, pick data tar ---
if [[ "$MODE" == "data" || "$MODE" == "both" ]]; then
  mapfile -t DATA_FILES < <(ls -1t "$BACKUP_DIR"/riven-data-*.tar.gz 2>/dev/null || true)
  if [[ ${#DATA_FILES[@]} -eq 0 ]]; then
    echo -e "${red}✗ No riven-data-*.tar.gz files found in $BACKUP_DIR${reset}"
    exit 1
  fi
  echo "Available app data backups:"
  select DATA_TAR in "${DATA_FILES[@]}"; do
    [[ -n "${DATA_TAR:-}" ]] && break
  done
  echo -e "→ Selected data archive: ${yellow}$(basename "$DATA_TAR")${reset}\n"
fi

# --- Confirmation(s) ---
echo "Summary of actions:"
[[ -n "$DB_DUMP"  ]] && echo "  - Restore DB from: $(basename "$DB_DUMP")"
[[ -n "$DATA_TAR" ]] && echo "  - Restore data from: $(basename "$DATA_TAR")"
read -rp "Proceed with these actions? (y/N): " confirm
[[ "${confirm,,}" == "y" ]] || { echo "Aborted."; exit 0; }

read -rp "⚠️  This will overwrite current data. Are you REALLY sure? (y/N): " really
[[ "${really,,}" == "y" ]] || { echo "Aborted."; exit 0; }

echo -e "\n${bold}${yellow}Starting restore process...${reset}\n"

# --- Always stop app to avoid write activity & reconnect issues ---
echo -e "[1/?] Stopping app container (${RIVEN_CONTAINER})…"
docker stop "$RIVEN_CONTAINER" || true

# --- If DB restore chosen: ensure DB up, recreate, restore ---
if [[ "$MODE" == "db" || "$MODE" == "both" ]]; then
  echo -e "[2/?] Ensuring DB container (${RIVEN_DB_CONTAINER}) is running…"
  docker start "$RIVEN_DB_CONTAINER" || true

  echo "      Waiting for Postgres to be ready…"
  for i in {1..30}; do
    if docker exec "$RIVEN_DB_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  echo -e "[3/?] Recreating database 'riven' (DROP + CREATE)…"
  docker exec -i -e PGPASSWORD=postgres "$RIVEN_DB_CONTAINER" \
    psql -U postgres -c "DROP DATABASE IF EXISTS riven;" >/dev/null
  docker exec -i -e PGPASSWORD=postgres "$RIVEN_DB_CONTAINER" \
    psql -U postgres -c "CREATE DATABASE riven;" >/dev/null
  echo -e "      ${green}✓ Fresh database created.${reset}"

  echo -e "[4/?] Restoring database from ${yellow}$(basename "$DB_DUMP")${reset}…"
  docker exec -i -e PGPASSWORD=postgres "$RIVEN_DB_CONTAINER" \
    pg_restore -U postgres -d riven --no-owner -F c < "$DB_DUMP"
  echo -e "      ${green}✓ Database restore complete.${reset}\n"
fi

# --- If data restore chosen: extract into bind mount ---
if [[ "$MODE" == "data" || "$MODE" == "both" ]]; then
  echo -e "[5/?] Restoring app data from ${yellow}$(basename "$DATA_TAR")${reset}…"
  mkdir -p "$RIVEN_DATA"
  tar xzf "$DATA_TAR" -C "$RIVEN_DATA"
  echo -e "      ${green}✓ App data restored to ${RIVEN_DATA}.${reset}\n"
fi

# --- Restart app ---
echo -e "[6/?] Starting app container (${RIVEN_CONTAINER})…"
docker start "$RIVEN_CONTAINER" || true
echo -e "      ${green}✓ App started.${reset}\n"

echo -e "${bold}${green}✅ Restore complete!${reset}"
[[ -n "$DB_DUMP"  ]] && echo -e "   Database: ${yellow}$(basename "$DB_DUMP")${reset}"
[[ -n "$DATA_TAR" ]] && echo -e "   Data:     ${yellow}$(basename "$DATA_TAR")${reset}"
