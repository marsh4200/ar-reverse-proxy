#!/usr/bin/env bash
#
# ar-reverse-proxy update script
# Called by the backend (via update_service.run_update) when the user clicks
# "Install update" in the GUI. Also runnable manually.
#
# Detaches from the parent (the FastAPI process we're about to restart),
# so we don't get killed mid-update.
#
set -euo pipefail

INSTALL_DIR="${ARRP_INSTALL_DIR:-/opt/ar-reverse-proxy}"
SERVICE_NAME="ar-reverse-proxy"
LOG="/var/log/ar-reverse-proxy-update.log"
GITHUB_BRANCH="${ARRP_GITHUB_BRANCH:-main}"

# Re-exec detached from parent so systemctl restart can't kill us mid-flight.
# Explicit /bin/bash so this works even if update.sh somehow lost its +x bit
# (which has happened: GitHub web-UI uploads strip the executable bit).
if [[ "${ARRP_UPDATE_DETACHED:-0}" != "1" ]]; then
    ARRP_UPDATE_DETACHED=1 nohup /bin/bash "$0" "$@" </dev/null >>"$LOG" 2>&1 &
    disown
    exit 0
fi

# From here on we're detached.
exec >>"$LOG" 2>&1

ts() { date '+%Y-%m-%d %H:%M:%S'; }
echo ""
echo "════════════════════════════════════════════════════════════"
echo "[$(ts)] Update started"
echo "════════════════════════════════════════════════════════════"

cd "$INSTALL_DIR"

# Give the backend a moment to send its HTTP response before we yank the rug
sleep 2

echo "[$(ts)] Fetching from origin/$GITHUB_BRANCH"
git fetch --quiet origin "$GITHUB_BRANCH"

OLD_SHA=$(git rev-parse HEAD)
git reset --hard "origin/$GITHUB_BRANCH"
NEW_SHA=$(git rev-parse HEAD)

if [[ "$OLD_SHA" == "$NEW_SHA" ]]; then
    echo "[$(ts)] Already at latest commit ($NEW_SHA) - restarting anyway"
else
    echo "[$(ts)] Updated $OLD_SHA -> $NEW_SHA"
fi

echo "[$(ts)] Updating Python dependencies"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade -r "$INSTALL_DIR/requirements.txt"

# If the systemd unit itself changed, reinstall it
if ! cmp -s "$INSTALL_DIR/systemd/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"; then
    echo "[$(ts)] systemd unit changed - reinstalling"
    install -m 644 "$INSTALL_DIR/systemd/${SERVICE_NAME}.service" \
        "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload
fi

echo "[$(ts)] Restarting service"
systemctl restart "$SERVICE_NAME"

sleep 3
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "[$(ts)] Service is up - update complete"
else
    echo "[$(ts)] WARN: service not active - check journalctl -u $SERVICE_NAME"
    exit 1
fi
