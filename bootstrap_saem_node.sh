#!/usr/bin/env bash
set -euo pipefail

# ====== CONFIG (EDIT THIS) ======
# URL al asset saem-node.tar.gz en GitHub Release (direct download)
SAEM_TARBALL_URL="https://github.com/AlejandroSlrio/saem-deploy/releases/download/v0.1.0/saem-node.tar.gz"
SAEM_TARBALL_SHA256_URL="https://github.com/AlejandroSlrio/saem-deploy/releases/download/v0.1.0/saem-node.tar.gz.sha256"
# ================================

echo "=== SAEM node bootstrap ==="
echo

read -rp "Node ID (e.g., saem_n2): " NODE_ID
read -rp "Collector URL base (e.g., http://140.xxx.xxx.xxx:8080): " COLLECTOR_BASE
read -rp "Token for ${NODE_ID}: " TOKEN

# Guardrails: evita “unbound variable” y entradas vacías
: "${NODE_ID:?missing NODE_ID}"
: "${COLLECTOR_BASE:?missing COLLECTOR_BASE}"
: "${TOKEN:?missing TOKEN}"

INGEST_URL="${COLLECTOR_BASE%/}/ingest"

echo
echo "Node ID      : $NODE_ID"
echo "Collector    : $COLLECTOR_BASE"
echo "Ingest URL   : $INGEST_URL"
echo "Token        : [hidden]"
echo

echo "[1/9] Installing system dependencies..."
apt update
apt install -y \
  sqlite3 alsa-utils libportaudio2 \
  curl ca-certificates \
  chrony

echo "[2/9] Setting timezone..."
timedatectl set-timezone Europe/Dublin

echo "[3/9] Configuring chrony..."
mkdir -p /etc/chrony/conf.d
cat >/etc/chrony/conf.d/saem.conf <<'EOF'
pool time.google.com iburst
pool pool.ntp.org iburst
makestep 1.0 3
rtcsync
EOF
systemctl enable --now chrony >/dev/null || true
systemctl restart chrony || true

echo "[4/9] Writing node identity..."
echo "$NODE_ID" > /etc/saem_node_id
chmod 644 /etc/saem_node_id

echo "[5/9] Creating SAEM directories..."
mkdir -p /opt/saem/{src,data,logs,state}

echo "[6/9] Downloading SAEM node package..."
curl -fL --retry 3 --retry-delay 1 -o /tmp/saem-node.tar.gz "$SAEM_TARBALL_URL"
curl -fL --retry 3 --retry-delay 1 -o /tmp/saem-node.tar.gz.sha256 "$SAEM_TARBALL_SHA256_URL"

echo "[7/9] Verifying checksum..."
cd /tmp
sha256sum -c saem-node.tar.gz.sha256

echo "[8/9] Installing SAEM node package..."
tar xzf /tmp/saem-node.tar.gz -C /

echo "[9/9] Configuring uploader + enabling services..."
UP="/opt/saem/src/uploader.py"

# Sanity check: uploader.py debe existir en el tarball
if [[ ! -f "$UP" ]]; then
  echo "ERROR: uploader not found at $UP"
  echo "Did the saem-node.tar.gz include /opt/saem/src/uploader.py ?"
  exit 1
fi

# TOKEN line (reemplaza TOKEN = "..."
sed -i -E "s/^TOKEN\s*=\s*\".*\"/TOKEN = \"${TOKEN}\"/g" "$UP"

# COLLECTOR_URL line (insert if missing)
if grep -qE '^COLLECTOR_URL\s*=' "$UP"; then
  sed -i -E "s|^COLLECTOR_URL\s*=\s*\".*\"|COLLECTOR_URL = \"${INGEST_URL}\"|g" "$UP"
else
  awk -v url="$INGEST_URL" '
    {print}
    /^TOKEN[[:space:]]*=/ {print "COLLECTOR_URL = \"" url "\""}
  ' "$UP" > /tmp/uploader.py && mv /tmp/uploader.py "$UP"
fi

systemctl daemon-reload
systemctl enable --now saem
systemctl enable --now saem-uploader

echo
echo "✅ Done."
echo "Quick checks:"
echo "  chronyc tracking"
echo "  timedatectl status"
echo "  systemctl status saem --no-pager -l"
echo "  systemctl status saem-uploader --no-pager -l"
echo "  tail -n 50 /opt/saem/logs/uploader.log"
