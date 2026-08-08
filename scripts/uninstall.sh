#!/usr/bin/env bash
#
# Apple Watch Challenge Radar - uninstaller
#
# Stops and disables the timer, removes systemd unit files, and reloads
# systemd. Data directories and the Conda environment are left untouched;
# the operator decides whether to remove them manually.

set -euo pipefail

SERVICE_NAME="apple-watch-challenge-radar"
ENV_NAME="apple-watch-challenge-radar"
STATE_DIR="/var/lib/apple-watch-challenge-radar"
OUTPUT_DIR="/var/www/apple-watch-challenges"

log()  { printf '\033[1;32m[uninstall]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
    die "run this uninstaller as root (sudo)"
fi

log "stopping and disabling timer"
systemctl stop "${SERVICE_NAME}.timer" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}.timer" 2>/dev/null || true

log "removing systemd unit files"
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
rm -f "/etc/systemd/system/${SERVICE_NAME}.timer"
systemctl daemon-reload

log "uninstall complete"
log "data kept at: ${STATE_DIR}"
log "ICS output kept at: ${OUTPUT_DIR}"
log "conda environment kept: ${ENV_NAME}"
log "to remove them manually:"
log "  rm -rf ${STATE_DIR} ${OUTPUT_DIR}"
log "  conda env remove -n ${ENV_NAME}"