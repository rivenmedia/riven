#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_DIR="/opt/riven-torbox"
readonly REPO_URL="https://github.com/laxnad/riven.git"
readonly REPO_BRANCH="feature/torbox"

info() { printf '\033[1;34m[INFO]\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "Run as root inside the Riven LXC."
[[ -f /run/systemd/container ]] || die "This recovery script must run inside the created LXC."

read -r -s -p "TorBox API key: " TORBOX_API_KEY
printf '\n'
[[ ${#TORBOX_API_KEY} -ge 20 ]] || die "The TorBox API key appears too short."
read -r -p "Timezone [Asia/Kolkata]: " TIMEZONE
TIMEZONE="${TIMEZONE:-Asia/Kolkata}"
read -r -p "Install Jellyfin in this LXC? [y/N]: " JELLYFIN_CHOICE
INSTALL_JELLYFIN=0
[[ ${JELLYFIN_CHOICE,,} == "y" || ${JELLYFIN_CHOICE,,} == "yes" ]] && INSTALL_JELLYFIN=1

info "Repairing package state and installing Docker (IPv4 forced)..."
export DEBIAN_FRONTEND=noninteractive
dpkg --configure -a
apt-get -o Acquire::ForceIPv4=true update
apt-get -o Acquire::ForceIPv4=true install -y ca-certificates curl git gnupg openssl
install -m 0755 -d /etc/apt/keyrings
curl -4 -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian %s stable\n' \
    "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
apt-get -o Acquire::ForceIPv4=true update
apt-get -o Acquire::ForceIPv4=true install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

info "Preparing application files..."
mkdir -p "$APP_DIR"
if [[ -d "$APP_DIR/app/.git" ]]; then
    git -C "$APP_DIR/app" fetch origin "$REPO_BRANCH"
    git -C "$APP_DIR/app" switch "$REPO_BRANCH"
    git -C "$APP_DIR/app" pull --ff-only origin "$REPO_BRANCH"
else
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR/app"
fi
mkdir -p "$APP_DIR/data" "$APP_DIR/db" "$APP_DIR/frontend" "$APP_DIR/jellyfin" "$APP_DIR/mount"
chown -R 1000:1000 "$APP_DIR/data" "$APP_DIR/mount"

umask 077
POSTGRES_PASSWORD="$(openssl rand -hex 24)"
cat > "$APP_DIR/.env" <<EOF
TORBOX_API_KEY=${TORBOX_API_KEY}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
TZ=${TIMEZONE}
PUID=1000
PGID=1000
EOF
unset TORBOX_API_KEY POSTGRES_PASSWORD

cat > "$APP_DIR/compose.yml" <<'EOF'
services:
  riven-frontend:
    image: spoked/riven-frontend:v1.0.0-beta.1
    container_name: riven-frontend
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      TZ: ${TZ:-Etc/UTC}
    volumes:
      - ./frontend:/riven/config
    depends_on:
      - riven

  riven:
    build:
      context: ./app
      dockerfile: Dockerfile
    image: laxnad/riven:torbox
    container_name: riven
    restart: unless-stopped
    ports:
      - "8080:8080"
    cap_add:
      - SYS_ADMIN
    security_opt:
      - apparmor:unconfined
    shm_size: 1024m
    devices:
      - /dev/fuse:/dev/fuse
    environment:
      PUID: ${PUID:-1000}
      PGID: ${PGID:-1000}
      TZ: ${TZ:-Etc/UTC}
      RIVEN_FORCE_ENV: "true"
      RIVEN_DATABASE_HOST: postgresql+psycopg2://postgres:${POSTGRES_PASSWORD}@riven-db/riven
      RIVEN_FILESYSTEM_MOUNT_PATH: /mount
      RIVEN_UPDATERS_LIBRARY_PATH: /mount
      RIVEN_DOWNLOADERS_TORBOX_ENABLED: "true"
      RIVEN_DOWNLOADERS_TORBOX_API_KEY: ${TORBOX_API_KEY}
    volumes:
      - ./data:/riven/data
      - ./mount:/mount:rshared
    depends_on:
      riven-db:
        condition: service_healthy

  riven-db:
    image: postgres:17-alpine
    container_name: riven-db
    restart: unless-stopped
    environment:
      PGDATA: /var/lib/postgresql/data/pgdata
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: riven
    volumes:
      - ./db:/var/lib/postgresql/data/pgdata
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d riven"]
      interval: 10s
      timeout: 5s
      retries: 10
EOF

if (( INSTALL_JELLYFIN == 1 )); then
cat >> "$APP_DIR/compose.yml" <<'EOF'

  jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: jellyfin
    user: "1000:1000"
    restart: unless-stopped
    ports:
      - "8096:8096"
    volumes:
      - ./jellyfin:/config
      - ./mount:/mount:rslave
EOF
fi

cat > /etc/systemd/system/riven-mount.service <<EOF
[Unit]
Description=Prepare Riven shared mount
Before=docker.service

[Service]
Type=oneshot
ExecStart=/bin/mount --bind ${APP_DIR}/mount ${APP_DIR}/mount
ExecStart=/bin/mount --make-rshared ${APP_DIR}/mount
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now riven-mount.service

info "Building and starting Riven..."
cd "$APP_DIR"
docker compose build
docker compose up -d

IP_ADDRESS="$(hostname -I | awk '{print $1}')"
ok "Recovery installation completed."
printf 'Riven UI:  http://%s:3000\n' "$IP_ADDRESS"
printf 'Riven API: http://%s:8080\n' "$IP_ADDRESS"
(( INSTALL_JELLYFIN == 1 )) && printf 'Jellyfin:  http://%s:8096\n' "$IP_ADDRESS"
printf 'Logs: cd %s && docker compose logs -f riven\n' "$APP_DIR"
