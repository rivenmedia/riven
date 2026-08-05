#!/usr/bin/env bash
set -Eeuo pipefail

# Riven + TorBox installer for a Proxmox VE host.
# Creates a privileged Debian LXC because nested Docker and FUSE are required.

readonly REPO_URL="https://github.com/laxnad/riven.git"
readonly REPO_BRANCH="feature/torbox"
readonly APP_DIR="/opt/riven-torbox"

info() { printf '\033[1;34m[INFO]\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "Run this script as root in the Proxmox VE host shell."
command -v pct >/dev/null || die "pct was not found. Run this on a Proxmox VE host."
command -v pvesh >/dev/null || die "pvesh was not found. Run this on a Proxmox VE host."

printf '\nRiven + TorBox Proxmox installer\n'
printf '%s\n' '--------------------------------'
warn "This creates a PRIVILEGED LXC with nesting and FUSE access."
warn "Only continue if you trust the containers and code run inside it."
read -r -p "Continue? [y/N]: " CONFIRM
[[ ${CONFIRM,,} == "y" || ${CONFIRM,,} == "yes" ]] || exit 0

DEFAULT_CTID="$(pvesh get /cluster/nextid)"
read -r -p "Container ID [${DEFAULT_CTID}]: " CTID
CTID="${CTID:-$DEFAULT_CTID}"
[[ $CTID =~ ^[0-9]+$ ]] || die "Container ID must be numeric."
if pct status "$CTID" >/dev/null 2>&1; then
    die "Container ${CTID} already exists; nothing was changed."
fi

read -r -p "Hostname [riven-torbox]: " HOSTNAME
HOSTNAME="${HOSTNAME:-riven-torbox}"
[[ $HOSTNAME =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || die "Invalid hostname."

mapfile -t ROOT_STORAGES < <(pvesm status -content rootdir | awk 'NR > 1 && $3 == "active" {print $1}')
(( ${#ROOT_STORAGES[@]} > 0 )) || die "No active Proxmox storage supports LXC root disks."
printf 'Root-disk storage options: %s\n' "${ROOT_STORAGES[*]}"
read -r -p "Root-disk storage [${ROOT_STORAGES[0]}]: " ROOT_STORAGE
ROOT_STORAGE="${ROOT_STORAGE:-${ROOT_STORAGES[0]}}"
printf '%s\n' "${ROOT_STORAGES[@]}" | grep -Fxq "$ROOT_STORAGE" || die "Storage does not support rootdir content."

mapfile -t TEMPLATE_STORAGES < <(pvesm status -content vztmpl | awk 'NR > 1 && $3 == "active" {print $1}')
(( ${#TEMPLATE_STORAGES[@]} > 0 )) || die "No active Proxmox storage supports container templates."
read -r -p "Template storage [${TEMPLATE_STORAGES[0]}]: " TEMPLATE_STORAGE
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-${TEMPLATE_STORAGES[0]}}"
printf '%s\n' "${TEMPLATE_STORAGES[@]}" | grep -Fxq "$TEMPLATE_STORAGE" || die "Storage does not support vztmpl content."

read -r -p "Disk size in GiB [32]: " DISK_GB
DISK_GB="${DISK_GB:-32}"
[[ $DISK_GB =~ ^[0-9]+$ ]] && (( DISK_GB >= 16 )) || die "Disk size must be at least 16 GiB."

read -r -p "CPU cores [4]: " CORES
CORES="${CORES:-4}"
[[ $CORES =~ ^[0-9]+$ ]] && (( CORES >= 2 )) || die "Use at least 2 CPU cores."

read -r -p "Memory in MiB [4096]: " MEMORY
MEMORY="${MEMORY:-4096}"
[[ $MEMORY =~ ^[0-9]+$ ]] && (( MEMORY >= 2048 )) || die "Use at least 2048 MiB RAM."

read -r -p "Network bridge [vmbr0]: " BRIDGE
BRIDGE="${BRIDGE:-vmbr0}"
ip link show "$BRIDGE" >/dev/null 2>&1 || die "Bridge ${BRIDGE} does not exist."

read -r -p "VLAN tag (leave blank for none): " VLAN_TAG
if [[ -n $VLAN_TAG ]]; then
    [[ $VLAN_TAG =~ ^[0-9]+$ ]] && (( VLAN_TAG >= 1 && VLAN_TAG <= 4094 )) || die "Invalid VLAN tag."
fi

read -r -p "IPv4 configuration [dhcp]: " IPV4
IPV4="${IPV4:-dhcp}"
NET0="name=eth0,bridge=${BRIDGE},ip=${IPV4},firewall=1"
[[ -n $VLAN_TAG ]] && NET0+=",tag=${VLAN_TAG}"
if [[ $IPV4 != "dhcp" ]]; then
    read -r -p "IPv4 gateway: " GATEWAY
    [[ -n $GATEWAY ]] || die "A gateway is required for static IPv4."
    NET0+=",gw=${GATEWAY}"
fi

read -r -p "Timezone [Asia/Kolkata]: " TIMEZONE
TIMEZONE="${TIMEZONE:-Asia/Kolkata}"
[[ -e "/usr/share/zoneinfo/${TIMEZONE}" ]] || die "Unknown timezone: ${TIMEZONE}"

read -r -s -p "TorBox API key: " TORBOX_API_KEY
printf '\n'
[[ ${#TORBOX_API_KEY} -ge 20 ]] || die "The TorBox API key appears too short."

read -r -p "Install Jellyfin in the same LXC? [Y/n]: " JELLYFIN_CHOICE
JELLYFIN_CHOICE="${JELLYFIN_CHOICE:-y}"
INSTALL_JELLYFIN=0
[[ ${JELLYFIN_CHOICE,,} == "y" || ${JELLYFIN_CHOICE,,} == "yes" ]] && INSTALL_JELLYFIN=1
if (( INSTALL_JELLYFIN == 0 )); then
    warn "An external media-server LXC cannot directly see this LXC's internal FUSE mount."
    warn "You will need to export the mount or move the media server into this LXC."
fi

info "Locating the latest Debian 12 LXC template..."
pveam update >/dev/null
TEMPLATE="$(pveam available --section system | awk '/debian-12-standard/ {print $2}' | sort -V | tail -n1)"
[[ -n $TEMPLATE ]] || die "No Debian 12 standard template was found."
if ! pveam list "$TEMPLATE_STORAGE" | awk 'NR > 1 {print $1}' | grep -Fq "/${TEMPLATE}$"; then
    info "Downloading ${TEMPLATE}..."
    pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"
fi
TEMPLATE_VOLUME="${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE}"

info "Creating LXC ${CTID}..."
pct create "$CTID" "$TEMPLATE_VOLUME" \
    --hostname "$HOSTNAME" \
    --ostype debian \
    --unprivileged 0 \
    --features nesting=1,keyctl=1,fuse=1 \
    --rootfs "${ROOT_STORAGE}:${DISK_GB}" \
    --cores "$CORES" \
    --memory "$MEMORY" \
    --swap 512 \
    --net0 "$NET0" \
    --onboot 1 \
    --startup order=30,up=30 \
    --timezone "$TIMEZONE" \
    --tags riven-torbox

CONF_FILE="/etc/pve/lxc/${CTID}.conf"
printf '%s\n' \
    'lxc.apparmor.profile: unconfined' \
    'lxc.cgroup2.devices.allow: c 10:229 rwm' \
    'lxc.mount.entry: /dev/fuse dev/fuse none bind,create=file' \
    >> "$CONF_FILE"

info "Starting LXC..."
pct start "$CTID"
for _ in {1..30}; do
    pct exec "$CTID" -- true >/dev/null 2>&1 && break
    sleep 2
done
pct exec "$CTID" -- true >/dev/null 2>&1 || die "The LXC did not become ready."

info "Installing Docker and build dependencies inside the LXC..."
pct exec "$CTID" -- bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update; apt-get install -y ca-certificates curl git gnupg openssl; install -m 0755 -d /etc/apt/keyrings; curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc; chmod a+r /etc/apt/keyrings/docker.asc; . /etc/os-release; echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list; apt-get update; apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; systemctl enable --now docker'

info "Preparing Riven configuration..."
pct exec "$CTID" -- bash -c "git clone --branch '${REPO_BRANCH}' '${REPO_URL}' '${APP_DIR}/app'"
pct exec "$CTID" -- mkdir -p "${APP_DIR}/data" "${APP_DIR}/db" "${APP_DIR}/frontend" "${APP_DIR}/jellyfin" "${APP_DIR}/mount"
pct exec "$CTID" -- chown -R 1000:1000 "${APP_DIR}/data" "${APP_DIR}/mount"

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
umask 077
POSTGRES_PASSWORD="$(openssl rand -hex 24)"
cat > "${TEMP_DIR}/.env" <<EOF
TORBOX_API_KEY=${TORBOX_API_KEY}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
TZ=${TIMEZONE}
PUID=1000
PGID=1000
EOF
cat > "${TEMP_DIR}/compose.yml" <<'EOF'
services:
  riven-frontend:
    image: spoked/riven-frontend:latest
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
cat >> "${TEMP_DIR}/compose.yml" <<'EOF'

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

pct push "$CTID" "${TEMP_DIR}/.env" "${APP_DIR}/.env" --perms 0600
pct push "$CTID" "${TEMP_DIR}/compose.yml" "${APP_DIR}/compose.yml" --perms 0644
unset TORBOX_API_KEY POSTGRES_PASSWORD

cat > "${TEMP_DIR}/riven-mount.service" <<EOF
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
pct push "$CTID" "${TEMP_DIR}/riven-mount.service" "/etc/systemd/system/riven-mount.service" --perms 0644
pct exec "$CTID" -- systemctl daemon-reload
pct exec "$CTID" -- systemctl enable --now riven-mount.service

info "Building your Riven TorBox image. This can take several minutes..."
pct exec "$CTID" -- bash -c "cd '${APP_DIR}' && docker compose build && docker compose up -d"
pct set "$CTID" --protection 1

IP_ADDRESS="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
printf '\n'
ok "Riven + TorBox has been installed."
printf 'LXC:       %s (%s)\n' "$CTID" "$HOSTNAME"
printf 'Riven UI:  http://%s:3000\n' "${IP_ADDRESS:-CONTAINER_IP}"
printf 'Riven API: http://%s:8080\n' "${IP_ADDRESS:-CONTAINER_IP}"
if (( INSTALL_JELLYFIN == 1 )); then
    printf 'Jellyfin:  http://%s:8096\n' "${IP_ADDRESS:-CONTAINER_IP}"
fi
printf 'App data:  %s inside LXC %s\n' "$APP_DIR" "$CTID"
printf '\nUseful host commands:\n'
printf '  pct exec %s -- bash -c %q\n' "$CTID" "cd ${APP_DIR} && docker compose ps"
printf '  pct exec %s -- bash -c %q\n' "$CTID" "cd ${APP_DIR} && docker compose logs -f riven"
if (( INSTALL_JELLYFIN == 0 )); then
    printf '\nRiven mount inside LXC %s: %s/mount\n' "$CTID" "$APP_DIR"
    printf 'External LXCs cannot consume it without an additional export/propagation setup.\n'
fi
