#!/bin/bash

set -e

echo "========================================="
echo " SAEM INSTALLER v1.1 (ROBUST)"
echo "========================================="

# =========================
# PRECHECK
# =========================
echo "[precheck] Checking time..."
date

echo "[precheck] Checking internet..."
ping -c 1 google.com > /dev/null || { echo "No internet"; exit 1; }

# =========================
# CONFIG
# =========================
echo "[config] Node configuration..."

read -p "Enter NODE_ID (e.g. saem-n3): " NODE_ID
read -p "Enter ROOM (e.g. room-3): " ROOM
read -p "Enter LOCATION (e.g. ot-3): " LOCATION

echo "[config] Using:"
echo "NODE_ID=$NODE_ID"
echo "ROOM=$ROOM"
echo "LOCATION=$LOCATION"

# =========================
# SYSTEM UPDATE
# =========================
echo "[0/9] Updating system..."
apt update

# =========================
# DEPENDENCIES
# =========================
echo "[1/9] Installing dependencies..."

apt install -y \
    python3 python3-pip python3-venv \
    git ffmpeg alsa-utils libsndfile1 curl \
    portaudio19-dev sox \
    build-essential zlib1g-dev libbz2-dev libreadline-dev \
    libsqlite3-dev libssl-dev libffi-dev libncurses-dev \
    xz-utils tk-dev libxml2-dev libxmlsec1-dev liblzma-dev

# =========================
# USER SETUP
# =========================
echo "[2/9] User setup..."

id -u saem &>/dev/null || useradd -m -s /bin/bash saem

usermod -aG audio saem

# =========================
# AUDIO CHECK
# =========================
echo "[3/9] Audio setup..."
arecord -l || true

# =========================
# TIME SYNC
# =========================
echo "[4/9] Time sync..."
timedatectl set-ntp true || true

# =========================
# TAILSCALE (optional)
# =========================
echo "[5/9] Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh

# =========================
# PYTHON ENV
# =========================
echo "[6/9] Python environment..."

mkdir -p /opt/saem
python3 -m venv /opt/saem/venv311

/opt/saem/venv311/bin/pip install --upgrade pip

/opt/saem/venv311/bin/pip install \
    numpy<2 scipy pandas sounddevice tflite-runtime

# =========================
# DEPLOY FILES
# =========================
echo "[7/9] Deploy files..."

mkdir -p /opt/nicu_audit

# 🔥 CLAVE: rsync limpio
rsync -av --delete nicu_audit/ /opt/nicu_audit/

# permisos
chown -R saem:saem /opt/nicu_audit

# =========================
# NODE ENV
# =========================
mkdir -p /opt/saem/config

cat > /opt/saem/config/node.env <<EOF
NODE_ID=$NODE_ID
ROOM=$ROOM
LOCATION=$LOCATION
EOF

chown -R saem:saem /opt/saem

# =========================
# FIFO (CRÍTICO)
# =========================
echo "[fifo] Creating FIFO..."

rm -f /tmp/saem_loudness_fifo
mkfifo /tmp/saem_loudness_fifo

chown saem:saem /tmp/saem_loudness_fifo
chmod 666 /tmp/saem_loudness_fifo

# =========================
# CLEAN OLD FILES
# =========================
echo "[cleanup] Removing legacy files..."

rm -f /opt/nicu_audit/data/*levels_1s_1s.csv || true

# =========================
# SAEM LIVE
# =========================
echo "[live] Installing saem-live..."

mkdir -p /opt/nicu_audit/bin

cp bin/saemcclive.sh /opt/nicu_audit/bin/
chmod +x /opt/nicu_audit/bin/saemcclive.sh

cat > /usr/local/bin/saem-live <<'EOF'
#!/bin/bash
/opt/nicu_audit/bin/saemcclive.sh
EOF

chmod +x /usr/local/bin/saem-live

# =========================
# SERVICES
# =========================
echo "[8/9] Deploy services..."

cp systemd/*.service /etc/systemd/system/

systemctl daemon-reload

systemctl enable nicu-audit
systemctl enable saem-loudness
systemctl enable saem-system-monitor

systemctl restart nicu-audit
systemctl restart saem-loudness
systemctl restart saem-system-monitor

# =========================
# HEALTH CHECK
# =========================
echo "========================================="
echo " SAEM STATUS"
echo "========================================="

echo "nicu-audit:"
systemctl is-active nicu-audit || true

echo "saem-loudness:"
systemctl is-active saem-loudness || true

echo "saem-system-monitor:"
systemctl is-active saem-system-monitor || true

echo "========================================="
echo " SAEM DEPLOYMENT COMPLETE"
echo "========================================="

echo "Next steps:"
echo "-----------------------------------------"
echo "1) Reboot recommended:"
echo "   sudo reboot"
echo ""
echo "2) Test:"
echo "   saem-live"
echo ""
echo "3) Logs:"
echo "   journalctl -u nicu-audit -f"
echo ""
echo "4) Optional Tailscale:"
echo "   sudo tailscale up"
echo "-----------------------------------------"
