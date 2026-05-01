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
  if [ "$arg" == "--full-update" ]; then
    FULL_UPDATE=true
  fi
done

# =========================
# PRECHECK: TIME SYNC
# =========================
echo "[precheck] Ensuring time sync..."
timedatectl set-ntp true || true
sleep 3
date

# =========================
# SYSTEM UPDATE
# =========================
echo "[0/9] Updating system..."
apt update

if [ "$FULL_UPDATE" = true ]; then
  echo "[0/9] Full upgrade..."
  apt upgrade -y
fi

# =========================
# NODE CONFIG (interactive or env)
# =========================
echo "[config] Node configuration..."

NODE_ID=${NODE_ID:-}
ROOM=${ROOM:-}
LOCATION=${LOCATION:-}

if [ -z "$NODE_ID" ]; then
  read -p "Enter NODE_ID (e.g. saem_n3): " NODE_ID
fi

if [ -z "$ROOM" ]; then
  read -p "Enter ROOM (e.g. room_3): " ROOM
fi

if [ -z "$LOCATION" ]; then
  read -p "Enter LOCATION (e.g. nicu_room_3): " LOCATION
fi

echo "[config] Using:"
echo "NODE_ID=$NODE_ID"
echo "ROOM=$ROOM"
echo "LOCATION=$LOCATION"

mkdir -p /opt/saem/config

cat <<EOF > /opt/saem/config/node.env
NODE_ID=$NODE_ID
ROOM=$ROOM
LOCATION=$LOCATION
EOF

# =========================
# DEPENDENCIES
# =========================
echo "[1/9] Dependencies"
bash scripts/install_dependencies.sh

# =========================
# USER SETUP
# =========================
echo "[2/9] User setup"
id -u saem &>/dev/null || useradd -m -s /bin/bash saem

# =========================
# AUDIO CHECK
# =========================
echo "[3/9] Audio setup"
arecord -l || true

# =========================
# TIME SYNC SERVICE
# =========================
echo "[4/9] Time sync"
systemctl enable systemd-timesyncd || true

# =========================
# TAILSCALE (optional)
# =========================
echo "[5/9] Tailscale"
if ! command -v tailscale &>/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
echo "👉 Run later: sudo tailscale up"

# =========================
# PYTHON ENV
# =========================
echo "[6/9] Python environment"
bash scripts/setup_venv.sh

# =========================
# FILE DEPLOY
# =========================
echo "[7/9] Deploy files"
bash scripts/deploy_files.sh

# =========================
# SERVICES
# =========================
echo "[8/9] Deploy services"

cp services/*.service /etc/systemd/system/

systemctl daemon-reload

systemctl enable nicu-audit
systemctl enable saem-loudness
systemctl enable saem-system-monitor

# =========================
# RUNTIME FIX
# =========================
echo "[runtime] Fixing runtime..."

mkdir -p /opt/nicu_audit/{logs,data}

touch /opt/nicu_audit/logs/nicu_audit.log
touch /opt/nicu_audit/logs/system_monitor.log
touch /opt/nicu_audit/logs/loudness.log

mkfifo /tmp/saem_audio_fifo 2>/dev/null || true
chown saem:saem /tmp/saem_audio_fifo
chmod 660 /tmp/saem_audio_fifo

chown -R saem:saem /opt/saem
chown -R saem:saem /opt/nicu_audit

chmod -R 755 /opt/saem
chmod -R 755 /opt/nicu_audit

# =========================
# SAEM LIVE COMMAND
# =========================
ln -sf /opt/nicu_audit/src/saemcclive.sh /usr/local/bin/saem-live
chmod +x /opt/nicu_audit/src/saemcclive.sh

# =========================
# START SERVICES
# =========================
systemctl restart nicu-audit || true
systemctl restart saem-loudness || true
systemctl restart saem-system-monitor || true

# =========================
# HEALTH CHECK
# =========================
echo "=== SAEM STATUS ==="

systemctl is-active nicu-audit || true
systemctl is-active saem-loudness || true
systemctl is-active saem-system-monitor || true

echo "========================================="
echo " SAEM DEPLOYMENT COMPLETE"
echo "========================================="

echo "Next steps:"
echo "-----------------------------------------"
echo "1) Connect Tailscale:"
echo "   sudo tailscale up"
echo ""
echo "2) Test live:"
echo "   saem-live"
echo ""
echo "3) Logs:"
echo "   journalctl -u nicu-audit -f"
echo "-----------------------------------------"
