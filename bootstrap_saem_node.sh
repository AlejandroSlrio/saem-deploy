#!/usr/bin/env bash
set -euo pipefail

# ===================== CONFIG (EDIT) =====================
RELEASE_BASE="https://github.com/AlejandroSlrio/saem-deploy/releases/download/v0.1.1"

# Node bundle must untar into /opt/saem (and may include systemd units)
SAEM_TARBALL_URL="${RELEASE_BASE}/saem-node.tar.gz"
SAEM_TARBALL_SHA256_URL="${RELEASE_BASE}/saem-node.tar.gz.sha256"
# =========================================================

TZ="Europe/Dublin"
SAEM_ROOT="/opt/saem"
VENV="${SAEM_ROOT}/venv311"
LOG_DIR="${SAEM_ROOT}/logs"
STATE_DIR="${SAEM_ROOT}/state"
NODE_ID_PATH="/etc/saem_node_id"

echo "=== SAEM node bootstrap ==="
echo

# ---------- Helpers ----------
die() { echo "❌ $*" >&2; exit 1; }
need_root() { [[ "${EUID}" -eq 0 ]] || die "Run as root (use: curl ... | sudo bash)"; }

read_tty() {
  # usage: read_tty "Prompt: " VAR_NAME
  local prompt="$1"
  local __var="$2"
  local val=""
  if [[ -t 0 ]]; then
    read -rp "${prompt}" val
  else
    read -rp "${prompt}" val </dev/tty
  fi
  printf -v "${__var}" '%s' "${val}"
}

cmd_exists() { command -v "$1" >/dev/null 2>&1; }

# ---------- Start ----------
need_root

# Inputs (safe even when piped)
read_tty "Node ID (e.g., saem_n2): " NODE_ID
read_tty "Collector URL base (e.g., http://10.0.0.10:8080): " COLLECTOR_BASE
read_tty "Token for ${NODE_ID}: " TOKEN

[[ -n "${NODE_ID}" ]] || die "missing NODE_ID"
[[ -n "${COLLECTOR_BASE}" ]] || die "missing COLLECTOR_BASE"
[[ -n "${TOKEN}" ]] || die "missing TOKEN"

INGEST_URL="${COLLECTOR_BASE%/}/ingest"

echo
echo "Node ID      : ${NODE_ID}"
echo "Collector    : ${COLLECTOR_BASE}"
echo "Ingest URL   : ${INGEST_URL}"
echo "Token        : [hidden]"
echo

echo "[1/9] System packages..."
apt update
apt install -y \
  curl ca-certificates \
  sqlite3 alsa-utils libportaudio2 \
  chrony \
  python3 python3-venv python3-pip

echo "[2/9] Timezone + chrony..."
if cmd_exists timedatectl; then
  timedatectl set-timezone "${TZ}" || true
fi

mkdir -p /etc/chrony/conf.d
cat >/etc/chrony/conf.d/saem.conf <<'EOF'
pool time.google.com iburst
pool pool.ntp.org iburst
makestep 1.0 3
rtcsync
EOF
systemctl enable --now chrony >/dev/null 2>&1 || true
systemctl restart chrony >/dev/null 2>&1 || true

echo "[3/9] Node identity..."
echo "${NODE_ID}" > "${NODE_ID_PATH}"
chmod 644 "${NODE_ID_PATH}"

echo "[4/9] SAEM directories..."
mkdir -p "${SAEM_ROOT}/"{src,data,logs,state,models}

echo "[5/9] Download SAEM node bundle..."
curl -fL --retry 3 --retry-delay 1 -o /tmp/saem-node.tar.gz "${SAEM_TARBALL_URL}"
curl -fL --retry 3 --retry-delay 1 -o /tmp/saem-node.tar.gz.sha256 "${SAEM_TARBALL_SHA256_URL}"

echo "[6/9] Verify checksum..."
( cd /tmp && sha256sum -c saem-node.tar.gz.sha256 ) || die "Checksum failed for saem-node.tar.gz"

echo "[7/9] Install SAEM node bundle..."
tar xzf /tmp/saem-node.tar.gz -C /
sync

echo "[8/9] Python venv (local, clean)..."
# Prefer Python 3.11 if present; otherwise fallback to python3
PYTHON_BIN=""
if command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.11)"
else
  PYTHON_BIN="$(command -v python3)"
fi
[[ -n "${PYTHON_BIN}" ]] || die "No python3 found after installing packages."

rm -rf "${VENV}"
"${PYTHON_BIN}" -m venv "${VENV}"

# Upgrade pip + deps (piwheels helps on Pi)
"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install \
  "numpy<2" scipy sounddevice requests \
  --extra-index-url https://www.piwheels.org/simple

# Try tflite-runtime (this MUST work for YAMNet)
if ! "${VENV}/bin/pip" install tflite-runtime --extra-index-url https://www.piwheels.org/simple; then
  echo
  echo "❌ tflite-runtime install failed."
  echo "This typically happens when your system Python is not supported (e.g., Python 3.13 on Debian trixie)."
  echo "Fix: use Raspberry Pi OS (Bookworm) with Python 3.11, or ensure python3.11 is installed and used."
  exit 1
fi

echo "[9/9] Configure uploader + enable services..."
UP="${SAEM_ROOT}/src/uploader.py"
[[ -f "${UP}" ]] || die "Missing ${UP} (did the tarball install correctly?)"

# Patch TOKEN
sed -i -E "s/^TOKEN\s*=\s*\".*\"/TOKEN = \"${TOKEN}\"/g" "${UP}" || true

# Patch COLLECTOR_URL (preferred)
if grep -qE '^COLLECTOR_URL\s*=' "${UP}"; then
  sed -i -E "s|^COLLECTOR_URL\s*=\s*\".*\"|COLLECTOR_URL = \"${INGEST_URL}\"|g" "${UP}"
else
  # Insert after TOKEN line if missing
  awk -v url="${INGEST_URL}" '
    {print}
    /^TOKEN[[:space:]]*=/ {print "COLLECTOR_URL = \"" url "\""}
  ' "${UP}" > /tmp/uploader.py && mv /tmp/uploader.py "${UP}"
fi

# Backwards-compat: if code still uses SERVER_URL, patch it too
if grep -qE '^SERVER_URL\s*=' "${UP}"; then
  sed -i -E "s|^SERVER_URL\s*=\s*\".*\"|SERVER_URL = \"${INGEST_URL}\"|g" "${UP}" || true
fi

# Ensure log/state dirs writable by the invoking user (if any)
LOGIN_USER="${SUDO_USER:-}"
if [[ -n "${LOGIN_USER}" && "${LOGIN_USER}" != "root" ]]; then
  chown -R "${LOGIN_USER}:${LOGIN_USER}" "${SAEM_ROOT}/src" || true
  chown -R "${LOGIN_USER}:${LOGIN_USER}" "${LOG_DIR}" "${STATE_DIR}" || true
fi

systemctl daemon-reload

# Enable services (they should exist if tarball shipped them)
systemctl enable --now saem || die "Failed to enable/start saem.service (is the unit in the tarball?)"
systemctl enable --now saem-uploader || die "Failed to enable/start saem-uploader.service (is the unit in the tarball?)"

echo
echo "✅ Done."
echo "Quick checks:"
echo "  python:        ${VENV}/bin/python --version"
echo "  yamnet files:  ls -lh ${SAEM_ROOT}/models/yamnet/ (should exist from tarball)"
echo "  chrony:        chronyc tracking | head"
echo "  services:      systemctl status saem saem-uploader --no-pager -l"
echo "  logs:          tail -n 50 ${SAEM_ROOT}/logs/saem.log ; tail -n 50 ${SAEM_ROOT}/logs/uploader.log"
