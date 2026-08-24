#!/usr/bin/env bash
#
# ar-reverse-proxy installer
# Usage:  curl -sSL https://your.domain/install.sh | bash
#         curl -sSL https://raw.githubusercontent.com/USER/ar-reverse-proxy/main/install.sh | bash
#
# Idempotent: safe to re-run. Won't clobber existing config or DB.
#
set -euo pipefail

# -------- CONFIGURE THESE FOR YOUR FORK ----------
GITHUB_REPO="${ARRP_GITHUB_REPO:-marsh4200/ar-reverse-proxy}"
GITHUB_BRANCH="${ARRP_GITHUB_BRANCH:-main}"
# -------------------------------------------------

INSTALL_DIR="/opt/ar-reverse-proxy"
DATA_DIR="/var/lib/ar-reverse-proxy"
ENV_DIR="/etc/ar-reverse-proxy"
SERVICE_NAME="ar-reverse-proxy"
PORT=9914

# Colors
C_CYAN='\033[1;36m'; C_GREEN='\033[1;32m'; C_RED='\033[1;31m'; C_DIM='\033[2m'; C_OFF='\033[0m'
log()  { echo -e "${C_CYAN}==>${C_OFF} $*"; }
ok()   { echo -e "${C_GREEN}  ✓${C_OFF} $*"; }
die()  { echo -e "${C_RED}  ✗${C_OFF} $*" >&2; exit 1; }

# --- Pre-flight ---
[[ $EUID -eq 0 ]] || die "Run as root (try: curl -sSL ... | sudo bash)"
command -v apt-get >/dev/null || die "This installer targets Debian/Ubuntu (apt-get not found)"

log "ar-reverse-proxy installer"
log "Repo: ${GITHUB_REPO}@${GITHUB_BRANCH}"

# --- Dependencies ---
log "Installing system packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip \
    nginx \
    certbot python3-certbot-nginx \
    git curl ca-certificates ufw >/dev/null
ok "System packages installed"

# --- Fetch source ---
log "Fetching source from GitHub…"
if [[ -d "$INSTALL_DIR/.git" ]]; then
    git -C "$INSTALL_DIR" fetch --quiet origin "$GITHUB_BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$GITHUB_BRANCH" --quiet
    ok "Updated existing checkout at $INSTALL_DIR"
else
    mkdir -p "$INSTALL_DIR"
    git clone --quiet --branch "$GITHUB_BRANCH" \
        "https://github.com/${GITHUB_REPO}.git" "$INSTALL_DIR"
    ok "Cloned to $INSTALL_DIR"
fi

# --- Python venv ---
log "Setting up Python virtualenv…"
if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip wheel
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
ok "Python dependencies installed"

# --- Directories ---
log "Preparing data and config directories…"
mkdir -p "$DATA_DIR" "$ENV_DIR"
chmod 750 "$DATA_DIR" "$ENV_DIR"
ok "Created $DATA_DIR and $ENV_DIR"

# --- Environment file (preserves SECRET_KEY across re-runs) ---
ENV_FILE="$ENV_DIR/env"
if [[ ! -f "$ENV_FILE" ]]; then
    log "Generating environment file with fresh SECRET_KEY…"
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    cat > "$ENV_FILE" <<EOF
# ar-reverse-proxy environment
# Do not commit this file. SECRET_KEY rotation will invalidate all sessions.
ARRP_SECRET_KEY=${SECRET_KEY}
ARRP_DATA_DIR=${DATA_DIR}
ARRP_INSTALL_DIR=${INSTALL_DIR}
ARRP_GITHUB_REPO=${GITHUB_REPO}
ARRP_GITHUB_BRANCH=${GITHUB_BRANCH}
ARRP_ADMIN_USER=admin
ARRP_ADMIN_PASS=admin
EOF
    chmod 600 "$ENV_FILE"
    ok "Wrote $ENV_FILE (default admin: admin / admin — CHANGE IT)"
else
    ok "Existing $ENV_FILE preserved"
fi

# --- systemd ---
log "Installing systemd unit…"
install -m 644 "$INSTALL_DIR/systemd/${SERVICE_NAME}.service" \
    "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1
ok "Service registered"

# --- nginx baseline ---
log "Configuring nginx…"
# Make sure the main directories exist (Ubuntu's nginx package creates these,
# but we're defensive).
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

# Ensure nginx.conf includes sites-enabled (Ubuntu default does, but verify)
if ! grep -q "sites-enabled" /etc/nginx/nginx.conf; then
    log "Patching nginx.conf to include sites-enabled…"
    sed -i '/http {/a \    include /etc/nginx/sites-enabled/*;' /etc/nginx/nginx.conf
fi

# Disable the distro-shipped default site. It sets `default_server`, so if
# it's left enabled it silently wins for any request whose Host header
# doesn't match one of our generated per-domain configs (bare IP hits,
# domains that haven't propagated yet, typos, ...) - which looks exactly
# like the reverse proxy "randomly" sending visitors to an unrelated page.
# ar-reverse-proxy installs its own default_server catch-all on startup
# (returns 444) so this doesn't leave port 80 without a default at all.
if [[ -e /etc/nginx/sites-enabled/default ]]; then
    log "Disabling distro default nginx site…"
    rm -f /etc/nginx/sites-enabled/default
    ok "Removed /etc/nginx/sites-enabled/default"
fi

systemctl enable nginx >/dev/null 2>&1
systemctl start nginx
nginx -t >/dev/null 2>&1 && ok "nginx config valid" || die "nginx -t failed"

# --- Firewall ---
log "Opening firewall ports…"
if command -v ufw >/dev/null; then
    ufw allow 80/tcp   >/dev/null 2>&1 || true
    ufw allow 443/tcp  >/dev/null 2>&1 || true
    ufw allow ${PORT}/tcp >/dev/null 2>&1 || true
    ok "ufw rules added (80, 443, ${PORT})"
fi

# --- Start service ---
log "Starting ${SERVICE_NAME}…"
systemctl restart "${SERVICE_NAME}"
sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    ok "Service is running"
else
    journalctl -u "${SERVICE_NAME}" -n 30 --no-pager >&2
    die "Service failed to start - see logs above"
fi

# --- Done ---
IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${C_GREEN}════════════════════════════════════════════════════════════════${C_OFF}"
echo -e "${C_GREEN}  ar-reverse-proxy is installed and running${C_OFF}"
echo -e "${C_GREEN}════════════════════════════════════════════════════════════════${C_OFF}"
echo ""
echo -e "  ${C_CYAN}URL:${C_OFF}      http://${IP}:${PORT}"
echo -e "  ${C_CYAN}Login:${C_OFF}    admin / admin   ${C_DIM}(change immediately)${C_OFF}"
echo -e "  ${C_CYAN}Logs:${C_OFF}     journalctl -u ${SERVICE_NAME} -f"
echo -e "  ${C_CYAN}Config:${C_OFF}   ${ENV_FILE}"
echo -e "  ${C_CYAN}Data:${C_OFF}     ${DATA_DIR}"
echo ""
