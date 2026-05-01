#!/bin/bash
set -e

echo "========================================="
echo " SAEM INSTALLER v1.0"
echo "========================================="

# =========================
# FLAGS
# =========================
FULL_UPDATE=false

for arg in "$@"; do
  if [ "$arg" = "--full-update" ]; then
    FULL_UPDATE=true
  fi
done

# =========================
# PRECHECK
# =========================
echo "[precheck] Checking time..."
timedatectl set-ntp true || true
sleep 3
date

echo "[precheck] Checking internet..."
ping -c 1 github.com >/dev/null 2>&1 || {
  echo "[ERROR] No internet connection or GitHub unreachable."
  exit 1
}

# =========================
# SYSTEM UPDATE
# =========================
echo "[0/9] Updating package lists..."
apt update

if [ "$FULL_UPDATE" = true ]; then
  echo "[0/9] Running full system upgrade..."
  apt upgrade -y
fi

# =========================
# NODE CONFIG
# =========================
echo "[config] Node configuration..."

NODE_ID=${NODE_ID:-}
ROOM=${ROOM:-}
LOCATION=${LOCATION:-}

if [ -z "$NODE_ID" ]; then
  read -p "Enter NODE_ID, e.g. saem-n3: " NODE_ID
fi

if [ -z "$ROOM" ]; then
  read -p "Enter ROOM, e.g. room-3: " ROOM
fi

if [ -z "$LOCATION" ]; then
  read -p "Enter LOCATION, e.g. ot-3: " LOCATION
fi

echo "[config] Using:"
echo "NODE_ID=$NODE_ID"
echo "ROOM=$ROOM"
echo "LOCATION=$LOCATION"

# =========================
# DEPENDENCIES
# =========================
echo "[1/9] Installing dependencies..."
bash scripts/install_dependencies.sh

# =========================
# USER SETUP
# =========================
echo "[2/9] Setting up user..."
id -u saem >/dev/null 2>&1 || useradd -m -s /bin/bash saem
usermod -aG audio saem

# =========================
# AUDIO CHECK
# =========================
echo "[3/9] Audio devices..."
arecord -l || true

# =========================
# TIME SYNC
# =========================
echo "[4/9] Time sync..."
systemctl enable systemd-timesyncd || true
systemctl restart systemd-timesyncd || true

# =========================
# TAILSCALE
# =========================
echo "[5/9] Tailscale..."
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
echo "Run later if needed: sudo tailscale up"

# =========================
# PYTHON ENV
# =========================
echo "[6/9] Python environment..."

rm -rf /opt/saem/venv311
mkdir -p /opt/saem

# IMPORTANT:
# We intentionally use pyenv/compiled Python 3.11 only as builder,
# then ensure /root/.pyenv is readable by the saem service user.
# This is required because Raspberry Pi OS Trixie ships Python 3.13,
# while tflite-runtime needs Python 3.11.
bash scripts/setup_venv.sh

chmod o+rx /root || true
chmod -R o+rx /root/.pyenv || true

# =========================
# FILE DEPLOY
# =========================
echo "[7/9] Deploy files..."
bash scripts/deploy_files.sh

# =========================
# NODE METADATA
# =========================
echo "[config] Writing node metadata..."

mkdir -p /opt/saem/config
mkdir -p /opt/nicu_audit/config

cat > /opt/saem/config/node.env <<EOF
NODE_ID=$NODE_ID
ROOM=$ROOM
LOCATION=$LOCATION
EOF

echo "$NODE_ID" > /etc/saem_node_id
echo "$LOCATION" > /etc/saem_location

cat > /opt/nicu_audit/config/node_config.json <<EOF
{
  "node_id": "$NODE_ID",
  "room": "$ROOM",
  "location": "$LOCATION"
}
EOF

# =========================
# FIFO PERSISTENCE
# =========================
echo "[runtime] Setting up FIFO persistence..."

cat > /etc/tmpfiles.d/saem.conf <<EOF
p /tmp/saem_loudness_fifo 0660 saem saem -
EOF

systemd-tmpfiles --create /etc/tmpfiles.d/saem.conf

# Safety fallback
rm -f /tmp/saem_loudness_fifo
mkfifo /tmp/saem_loudness_fifo
chown saem:saem /tmp/saem_loudness_fifo
chmod 660 /tmp/saem_loudness_fifo

# =========================
# SERVICES
# =========================
echo "[8/9] Deploy services..."

cp services/*.service /etc/systemd/system/
systemctl daemon-reload

systemctl enable nicu-audit.service
systemctl enable saem-loudness.service
systemctl enable saem-system-monitor.service

# =========================
# RUNTIME DIRECTORIES
# =========================
echo "[runtime] Fixing runtime directories and permissions..."

mkdir -p /opt/nicu_audit/logs
mkdir -p /opt/nicu_audit/data
mkdir -p /opt/nicu_audit/meta
mkdir -p /opt/nicu_audit/summary

touch /opt/nicu_audit/logs/nicu_audit.log
touch /opt/nicu_audit/logs/loudness.log
touch /opt/nicu_audit/logs/system_monitor.log

chown -R saem:saem /opt/saem
chown -R saem:saem /opt/nicu_audit
chmod -R 755 /opt/saem
chmod -R 755 /opt/nicu_audit

chown saem:saem /tmp/saem_loudness_fifo
chmod 660 /tmp/saem_loudness_fifo

# =========================
# SAEM LIVE
# =========================
echo "[live] Installing saem-live..."

mkdir -p /opt/nicu_audit/bin

if [ -f "bin/saemcclive.sh" ]; then
  cp bin/saemcclive.sh /opt/nicu_audit/bin/saemcclive.sh
else
  cp /opt/nicu_audit/src/saemcclive.sh /opt/nicu_audit/bin/saemcclive.sh
fi

chmod +x /opt/nicu_audit/bin/saemcclive.sh
chown saem:saem /opt/nicu_audit/bin/saemcclive.sh

cat > /usr/local/bin/saem-live <<'EOF'
#!/bin/bash
/opt/nicu_audit/bin/saemcclive.sh
EOF

chmod +x /usr/local/bin/saem-live

# =========================
# START SERVICES
# =========================
echo "[9/9] Starting services..."

systemctl restart saem-system-monitor.service || true
systemctl restart nicu-audit.service || true
sleep 5
systemctl restart saem-loudness.service || true

# =========================
# HEALTH CHECK
# =========================
echo "========================================="
echo " SAEM STATUS"
echo "========================================="

echo "nicu-audit:"
systemctl is-active nicu-audit.service || true

echo "saem-loudness:"
systemctl is-active saem-loudness.service || true

echo "saem-system-monitor:"
systemctl is-active saem-system-monitor.service || true

echo "========================================="
echo " SAEM DEPLOYMENT COMPLETE"
echo "========================================="

echo "Next steps:"
echo "-----------------------------------------"
echo "1) Reboot is recommended because user 'saem' was added to audio group:"
echo "   sudo reboot"
echo ""
echo "2) After reboot, test:"
echo "   saem-live"
echo ""
echo "3) Check logs:"
echo "   journalctl -u nicu-audit -f"
echo "   journalctl -u saem-loudness -f"
echo ""
echo "4) Optional Tailscale:"
echo "   sudo tailscale up"
echo "-----------------------------------------"
