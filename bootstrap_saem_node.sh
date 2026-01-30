#!/usr/bin/env bash
set -euo pipefail

# ===================== CONFIG (EDIT) =====================
RELEASE_BASE="https://github.com/AlejandroSlrio/saem-deploy/releases/download/v0.1.0"

# Node bundle (tarball must untar into /opt/saem + /etc/systemd/system/*.service etc)
SAEM_TARBALL_URL="${RELEASE_BASE}/saem-node.tar.gz"
SAEM_TARBALL_SHA256_URL="${RELEASE_BASE}/saem-node.tar.gz.sha256"

# YAMNet assets in the SAME release
YAMNET_TFLITE_URL="${RELEASE_BASE}/yamnet.tflite"
YAMNET_CLASSMAP_URL="${RELEASE_BASE}/yamnet_class_map.csv"
# =========================================================

TZ="Europe/Dublin"
SAEM_ROOT="/opt/saem"
VENV="${SAEM_ROOT}/venv311"
MODELS_DIR="${SAEM_ROOT}/models/yamnet"
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

ensure_line_in_file() {
  # ensure_line_in_file "line" "file"
  local line="$1" file="$2"
  grep -qxF "$line" "$file" 2>/dev/null || echo "$line" >> "$file"
}

# ---------- Start ----------
need_root

# Inputs (safe even when piped)
read_tty "Node ID (e.g., saem_n2): " NODE_ID
read_tty "Collector URL base (e.g., http://140.xxx.xxx.xxx:8080): " COLLECTOR_BASE
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

echo "[1/10] System packages..."
apt update
apt install -y \
  curl ca-certificates \
  sqlite3 alsa-utils libportaudio2 \
  chrony \
  git build-essential \
  libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
  libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

echo "[2/10] Timezone + chrony..."
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

echo "[3/10] Node identity..."
echo "${NODE_ID}" > "${NODE_ID_PATH}"
chmod 644 "${NODE_ID_PATH}"

echo "[4/10] SAEM directories..."
mkdir -p "${SAEM_ROOT}/"{src,data,logs,state,models}
mkdir -p "${MODELS_DIR}"

echo "[5/10] Download SAEM node bundle..."
curl -fL --retry 3 --retry-delay 1 -o /tmp/saem-node.tar.gz "${SAEM_TARBALL_URL}"
curl -fL --retry 3 --retry-delay 1 -o /tmp/saem-node.tar.gz.sha256 "${SAEM_TARBALL_SHA256_URL}"

echo "[6/10] Verify checksum..."
( cd /tmp && sha256sum -c saem-node.tar.gz.sha256 ) || die "Checksum failed for saem-node.tar.gz"

echo "[7/10] Install SAEM node bundle..."
tar xzf /tmp/saem-node.tar.gz -C /
sync

echo "[8/10] Ensure YAMNet assets..."
curl -fL --retry 3 --retry-delay 1 -o "${MODELS_DIR}/yamnet.tflite" "${YAMNET_TFLITE_URL}"
curl -fL --retry 3 --retry-delay 1 -o "${MODELS_DIR}/yamnet_class_map.csv" "${YAMNET_CLASSMAP_URL}"

# ---------- Python strategy: force 3.11.9 via pyenv ----------
echo "[9/10] Python 3.11 venv (auto, no manual steps)..."

# We prefer: user pyenv python 3.11.9 (avoids cp313 tflite-runtime problem)
# Detect the *login user* even when running under sudo
LOGIN_USER="${SUDO_USER:-root}"
if [[ "${LOGIN_USER}" == "root" ]]; then
  die "This script should be run via sudo by a normal user (e.g., saem-n2), not as root login."
fi

USER_HOME="$(getent passwd "${LOGIN_USER}" | cut -d: -f6)"
PYENV_ROOT="${USER_HOME}/.pyenv"
PY311="${PYENV_ROOT}/versions/3.11.9/bin/python"

# Install pyenv if missing
if [[ ! -x "${PYENV_ROOT}/bin/pyenv" ]]; then
  echo "  - Installing pyenv for ${LOGIN_USER}..."
  sudo -u "${LOGIN_USER}" bash -lc 'curl -fsSL https://pyenv.run | bash'
fi

# Ensure shell init lines exist
BASHRC="${USER_HOME}/.bashrc"
ensure_line_in_file 'export PYENV_ROOT="$HOME/.pyenv"' "${BASHRC}"
ensure_line_in_file 'export PATH="$PYENV_ROOT/bin:$PATH"' "${BASHRC}"
ensure_line_in_file 'eval "$(pyenv init -)"' "${BASHRC}"

# Install Python 3.11.9 if needed
if [[ ! -x "${PY311}" ]]; then
  echo "  - Installing Python 3.11.9 with pyenv (this may take a while)..."
  sudo -u "${LOGIN_USER}" bash -lc 'export PYENV_ROOT="$HOME/.pyenv"; export PATH="$PYENV_ROOT/bin:$PATH"; eval "$(pyenv init -)"; pyenv install -s 3.11.9'
fi

[[ -x "${PY311}" ]] || die "Python 3.11.9 not found at ${PY311}"

# Recreate venv cleanly under /opt/saem
rm -rf "${VENV}"
"${PY311}" -m venv "${VENV}"

# Install python deps (use piwheels)
"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install \
  "numpy<2" scipy sounddevice requests \
  --extra-index-url https://www.piwheels.org/simple

# tflite-runtime must work under cp311 on Pi; if it fails, we stop with a clear error.
"${VENV}/bin/pip" install \
  tflite-runtime \
  --extra-index-url https://www.piwheels.org/simple || die "tflite-runtime install failed. This usually means you're not on a supported Python/arch."

echo "[10/10] Configure uploader + enable services..."

UP="${SAEM_ROOT}/src/uploader.py"
[[ -f "${UP}" ]] || die "Missing ${UP} (did the tarball install correctly?)"

# Patch TOKEN
sed -i -E "s/^TOKEN\s*=\s*\".*\"/TOKEN = \"${TOKEN}\"/g" "${UP}"

# Patch/insert COLLECTOR_URL
if grep -qE '^COLLECTOR_URL\s*=' "${UP}"; then
  sed -i -E "s|^COLLECTOR_URL\s*=\s*\".*\"|COLLECTOR_URL = \"${INGEST_URL}\"|g" "${UP}"
else
  awk -v url="${INGEST_URL}" '
    {print}
    /^TOKEN[[:space:]]*=/ {print "COLLECTOR_URL = \"" url "\""}
  ' "${UP}" > /tmp/uploader.py && mv /tmp/uploader.py "${UP}"
fi

# Make sure log/state dirs are writable by the login user (avoid weird permission issues)
chown -R "${LOGIN_USER}:${LOGIN_USER}" "${SAEM_ROOT}/src" || true
chown -R "${LOGIN_USER}:${LOGIN_USER}" "${LOG_DIR}" "${STATE_DIR}" || true

systemctl daemon-reload

# Services should use the venv python we just created
systemctl enable --now saem
systemctl enable --now saem-uploader

echo
echo "✅ Done."
echo "Quick checks:"
echo "  python:        ${VENV}/bin/python --version"
echo "  yamnet files:  ls -lh ${MODELS_DIR}/"
echo "  chrony:        chronyc tracking | head"
echo "  services:      systemctl status saem saem-uploader --no-pager -l"
echo "  logs:          tail -n 50 ${SAEM_ROOT}/logs/saem.log ; tail -n 50 ${SAEM_ROOT}/logs/uploader.log"
