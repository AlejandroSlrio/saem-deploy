#!/usr/bin/env bash
set -euo pipefail

# ================= CONFIG =================
RELEASE_TAG="v0.1.0"
REPO_BASE="https://github.com/AlejandroSlrio/saem-deploy/releases/download/${RELEASE_TAG}"

SAEM_TARBALL_URL="${REPO_BASE}/saem-node.tar.gz"
SAEM_TARBALL_SHA256_URL="${REPO_BASE}/saem-node.tar.gz.sha256"

YAMNET_TFLITE_URL="${REPO_BASE}/yamnet.tflite"
YAMNET_CLASSMAP_URL="${REPO_BASE}/yamnet_class_map.csv"
# ==========================================

echo "=== SAEM node bootstrap ==="
echo

read -rp "Node ID (e.g., saem_n2): " NODE_ID </dev/tty
read -rp "Collector base URL (e.g., http://140.xxx.xxx.xxx:8080): " COLLECTOR_BASE </dev/tty
read -rp "Token for ${NODE_ID}: " TOKEN </dev/tty

: "${NODE_ID:?missing NODE_ID}"
: "${COLLECTOR_BASE:?missing COLLECTOR_BASE}"
: "${TOKEN:?missing TOKEN}"

INGEST_URL="${COLLECTOR_BASE%/}/ingest"

echo
echo "Node ID    : $NODE_ID"
echo "Collector  : $COLLECTOR_BASE"
echo "Ingest URL : $INGEST_URL"
echo "Token      : [hidden]"
echo

echo "[1/10] Installing system packages..."
apt update
apt install -y \
  build-essential curl ca-certificates \
  sqlite3 alsa-utils libportaudio2 \
  libssl-dev libffi-dev \
  chrony

echo "[2/10] Timezone + chrony..."
timedatectl set-timezone Europe/Dublin
mkdir -p /etc/chrony/conf.d
cat >/etc/chrony/conf.d/saem.conf <<'EOF'
pool time.google.com iburst
pool pool.ntp.org iburst
makestep 1.0 3
rtcsync
EOF
systemctl enable --now chrony

echo "[3/10] Node identity..."
echo "$NODE_ID" > /etc/saem_node_id
chmod 644 /etc/saem_node_id

echo "[4/10] SAEM directories..."
mkdir -p /opt/saem/{src,data,logs,state,models/yamnet}
chown -R root:root /opt/saem

echo "[5/10] Download SAEM node package..."
curl -fL -o /tmp/saem-node.tar.gz "$SAEM_TARBALL_URL"
curl -fL -o /tmp/saem-node.tar.gz.sha256 "$SAEM_TARBALL_SHA256_URL"
(cd /tmp && sha256sum -c saem-node.tar.gz.sha256)
tar xzf /tmp/saem-node.tar.gz -C /

echo "[6/10] Download YAMNet models..."
curl -fL -o /opt/saem/models/yamnet/yamnet.tflite "$YAMNET_TFLITE_URL"
curl -fL -o /opt/saem/models/yamnet/yamnet_class_map.csv "$YAMNET_CLASSMAP_URL"

echo "[7/10] Python venv (local, clean)..."
PYTHON_BIN="$(command -v python3.11 || command -v python3)"
$PYTHON_BIN -m venv /opt/saem/venv311

/opt/saem/venv311/bin/pip install --upgrade pip
/opt/saem/venv311/bin/pip install \
  "numpy<2" scipy sounddevice requests \
  --extra-index-url https://www.piwheels.org/simple
/opt/saem/venv311/bin/pip install \
  tflite-runtime \
  --extra-index-url https://www.piwheels.org/simple

echo "[8/10] Configure uploader..."
UP="/opt/saem/src/uploader.py"

sed -i -E "s|^TOKEN\s*=.*|TOKEN = \"${TOKEN}\"|" "$UP"

if grep -q '^COLLECTOR_URL' "$UP"; then
  sed -i -E "s|^COLLECTOR_URL\s*=.*|COLLECTOR_URL = \"${INGEST_URL}\"|" "$UP"
else
  sed -i "/^TOKEN/a COLLECTOR_URL = \"${INGEST_URL}\"" "$UP"
fi

echo "[9/10] Systemd services..."
systemctl daemon-reload
systemctl enable saem
systemctl enable saem-uploader
systemctl restart saem
systemctl restart saem-uploader

echo "[10/10] Done 🎉"
echo
echo "Checks:"
echo "  systemctl status saem --no-pager"
echo "  systemctl status saem-uploader --no-pager"
echo "  chronyc tracking"
echo "  tail -n 50 /opt/saem/logs/uploader.log"
