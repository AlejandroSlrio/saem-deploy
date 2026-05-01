#!/bin/bash

set -e

echo "========================================="
echo " SAEM INSTALLER v1.4 (PRODUCTION)"
echo "========================================="

# =========================
# CONFIG
# =========================
read -p "Enter NODE_ID (e.g. saem-n3): " NODE_ID
read -p "Enter ROOM (e.g. room-3): " ROOM
read -p "Enter LOCATION (e.g. ot-3): " LOCATION

echo "[config]"
echo "NODE_ID=$NODE_ID"
echo "ROOM=$ROOM"
echo "LOCATION=$LOCATION"

# =========================
# UPDATE
# =========================
echo "[1/10] Updating system..."
sudo apt update

# =========================
# DEPENDENCIES
# =========================
echo "[2/10] Installing dependencies..."

sudo apt install -y \
    git curl build-essential \
    ffmpeg alsa-utils libsndfile1 \
    libportaudio2 portaudio19-dev \
    libasound2-dev sox \
    libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev \
    libsqlite3-dev libffi-dev \
    libncurses-dev liblzma-dev

# =========================
# USER
# =========================
echo "[3/10] User setup..."
sudo usermod -aG audio $USER

# =========================
# PYENV
# =========================
echo "[4/10] Installing pyenv..."

if [ ! -d "$HOME/.pyenv" ]; then
    curl https://pyenv.run | bash
fi

export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"

# persist
grep -q 'pyenv init' ~/.bashrc || echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.bashrc
grep -q 'pyenv init' ~/.bashrc || echo 'eval "$(pyenv init -)"' >> ~/.bashrc

# =========================
# PYTHON 3.11
# =========================
echo "[5/10] Installing Python 3.11..."

pyenv install -s 3.11.9
pyenv global 3.11.9

python -V

# =========================
# FOLDERS
# =========================
echo "[6/10] Creating folders..."

sudo rm -rf /opt/saem
sudo rm -rf /opt/nicu_audit

sudo mkdir -p /opt/saem
sudo mkdir -p /opt/nicu_audit

sudo chown -R $USER:$USER /opt/saem
sudo chown -R $USER:$USER /opt/nicu_audit

# =========================
# VENV
# =========================
echo "[7/10] Creating venv..."

python -m venv /opt/saem/venv311

/opt/saem/venv311/bin/pip install --upgrade pip

echo "[deps] Installing Python packages..."

/opt/saem/venv311/bin/pip install \
    numpy==1.26.4 \
    scipy \
    pandas \
    sounddevice

# 🔥 tflite separado (CRÍTICO)
echo "[deps] Installing tflite-runtime..."

/opt/saem/venv311/bin/pip install \
    tflite-runtime==2.14.0 \
    --extra-index-url https://www.piwheels.org/simple

# =========================
# COPY FILES
# =========================
echo "[8/10] Copying project files..."

cp -r nicu_audit/* /opt/nicu_audit/
cp -r external/* /opt/saem/
cp -r models/* /opt/saem/models/
cp -r bin/* /opt/nicu_audit/bin/

# =========================
# NODE CONFIG
# =========================
echo "[config] Writing node.env..."

mkdir -p /opt/saem/config

cat <<EOF > /opt/saem/config/node.env
NODE_ID=$NODE_ID
ROOM=$ROOM
LOCATION=$LOCATION
EOF

# =========================
# FIFO SERVICE (robusto)
# =========================
echo "[9/10] Creating FIFO service..."

cat <<EOF | sudo tee /etc/systemd/system/saem-fifo-setup.service
[Unit]
Description=SAEM FIFO Setup
Before=nicu-audit.service saem-loudness.service

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'rm -f /tmp/saem_loudness_fifo && mkfifo /tmp/saem_loudness_fifo && chmod 666 /tmp/saem_loudness_fifo'

[Install]
WantedBy=multi-user.target
EOF

# =========================
# SERVICES
# =========================
echo "[10/10] Installing services..."

if [ -d "services" ]; then
    sudo cp services/*.service /etc/systemd/system/
else
    echo "[ERROR] services folder missing"
    exit 1
fi

sudo systemctl daemon-reload

sudo systemctl enable saem-fifo-setup
sudo systemctl enable nicu-audit
sudo systemctl enable saem-loudness
sudo systemctl enable saem-system-monitor

sudo systemctl start saem-fifo-setup
sleep 2

sudo systemctl start nicu-audit
sudo systemctl start saem-loudness
sudo systemctl start saem-system-monitor

# =========================
# HEALTH CHECK
# =========================
echo "========================================="
echo " SAEM STATUS"
echo "========================================="

systemctl is-active nicu-audit
systemctl is-active saem-loudness
systemctl is-active saem-system-monitor

echo "========================================="
echo " INSTALL COMPLETE"
echo "========================================="

echo "Next steps:"
echo "-----------------------------------------"
echo "sudo reboot"
echo "saem-live"
