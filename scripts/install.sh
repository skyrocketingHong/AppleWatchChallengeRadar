#!/usr/bin/env bash
#
# Apple Watch Challenge Radar - Debian installer
#
# Responsibilities:
#   - verify Debian environment and conda
#   - create/update the Conda environment
#   - install the Python package
#   - create data/output directories with correct ownership
#   - install systemd service + timer
#   - daemon-reload, run bootstrap (or prompt), enable the timer
#
# Explicitly forbidden:
#   - modifying the user's Caddyfile
#   - installing Docker
#   - touching other Conda environments

set -euo pipefail

PROJECT_DIR="/opt/apple-watch-challenge-radar"
ENV_NAME="apple-watch-challenge-radar"
STATE_DIR="/var/lib/apple-watch-challenge-radar"
OUTPUT_DIR="/var/www/apple-watch-challenges"
SERVICE_NAME="apple-watch-challenge-radar"

log()  { printf '\033[1;32m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Privilege check
# ---------------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    die "run this installer as root (sudo)"
fi

# ---------------------------------------------------------------------------
# 1. Environment checks
# ---------------------------------------------------------------------------
if ! grep -qi 'debian' /etc/os-release 2>/dev/null; then
    warn "target OS is not Debian; continuing anyway"
fi

CONDA_BIN="$(command -v conda || true)"
if [ -z "${CONDA_BIN}" ]; then
    die "conda not found in PATH; install Miniconda first"
fi
log "conda: ${CONDA_BIN}"

if [ ! -d "${PROJECT_DIR}" ]; then
    die "project not found at ${PROJECT_DIR}; clone the repository there first"
fi
if [ ! -f "${PROJECT_DIR}/environment.yml" ]; then
    die "environment.yml missing in ${PROJECT_DIR}"
fi

# ---------------------------------------------------------------------------
# 2. Conda environment
# ---------------------------------------------------------------------------
if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
    log "updating conda environment ${ENV_NAME}"
    conda env update -n "${ENV_NAME}" -f "${PROJECT_DIR}/environment.yml" --prune
else
    log "creating conda environment ${ENV_NAME}"
    conda env create -f "${PROJECT_DIR}/environment.yml"
fi

ENV_PREFIX="$(
  conda run -n "${ENV_NAME}" python -c 'import sys; print(sys.prefix)'
)"
log "environment prefix: ${ENV_PREFIX}"

# ---------------------------------------------------------------------------
# 3. Install the package
# ---------------------------------------------------------------------------
log "installing package"
(
    cd "${PROJECT_DIR}"
    conda run -n "${ENV_NAME}" python -m pip install .
)

CLI_BIN="${ENV_PREFIX}/bin/challenge-radar"
if [ ! -x "${CLI_BIN}" ]; then
    die "challenge-radar CLI not found at ${CLI_BIN}"
fi

# ---------------------------------------------------------------------------
# 4. Runtime user, directories, permissions
# ---------------------------------------------------------------------------
RUN_USER="${SUDO_USER:-root}"
RUN_GROUP="$(id -gn "${RUN_USER}")"
log "runtime user: ${RUN_USER} (group ${RUN_GROUP})"

mkdir -p "${STATE_DIR}" "${OUTPUT_DIR}"
chown -R "${RUN_USER}:${RUN_GROUP}" "${STATE_DIR}" "${OUTPUT_DIR}"

# ---------------------------------------------------------------------------
# 5. systemd unit files
# ---------------------------------------------------------------------------
log "writing systemd unit files"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Apple Watch Challenge Radar
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${CLI_BIN} update
NoNewPrivileges=true
PrivateTmp=true
ReadWritePaths=${STATE_DIR}
ReadWritePaths=${OUTPUT_DIR}
EOF

cat > "/etc/systemd/system/${SERVICE_NAME}.timer" <<EOF
[Unit]
Description=Apple Watch Challenge Radar Hourly Check

[Timer]
OnCalendar=*-*-* *:17:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload

# ---------------------------------------------------------------------------
# 6. Bootstrap
# ---------------------------------------------------------------------------
if "${CLI_BIN}" status >/dev/null 2>&1; then
    log "status check passed; skipping bootstrap"
else
    log "running first-time bootstrap (no historical notifications)"
    sudo -u "${RUN_USER}" "${CLI_BIN}" bootstrap \
        || die "bootstrap failed; fix the error and re-run the installer"
fi

# ---------------------------------------------------------------------------
# 7. Enable timer
# ---------------------------------------------------------------------------
systemctl enable --now "${SERVICE_NAME}.timer"
log "timer enabled: ${SERVICE_NAME}.timer (hourly, ~minute 17 + jitter)"

log "install complete"
log "ICS output: ${OUTPUT_DIR}"
log "logs: journalctl -u ${SERVICE_NAME}.service -n 200"
log "manual run: systemctl start ${SERVICE_NAME}.service"