#!/bin/bash

set -e

echo "========================================="
echo " SAEM INSTALLER v1.5 (IDEMPOTENT)"
echo "========================================="

# =========================
# CONFIG
# =========================
read -p "NODE_ID: " NODE_ID
read -p "ROOM: " ROOM
read -p "LOCATION: " LOCATION

echo "[config]"
echo "NODE_ID=$NODE_ID"
echo "ROOM=$ROOM"
echo "LOCATION=$LOCATION"

# =========================
# SYSTEM UPDATE
# =========================
echo "[1/10] Updating system..."
sudo apt update -y

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
# USER PERMISSIONS
# =========================
echo "[3/10] User setup..."
sudo usermod -aG audio $USER || true

# =========================
# PYENV
# =========================
echo "[4/10] Setting up pyenv..."

if [ ! -d "$HOME/.pyenv" ]; then
    curl https://pyenv.run | bash
fi

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

eval "$(pyenv init -)"

# persist (idempotente)
grep -q PYENV_ROOT ~/.bashrc || echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
grep -q 'pyenv init' ~/.bashrc || echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
grep -q 'pyenv init' ~/.bashrc || echo 'eval "$(pyenv init -)"' >> ~/.bashrc

# =========================
# PYTHON 3.11
# =========================
echo "[5/10] Ensuring Python 3.11..."

pyenv install -s 3.11.9
pyenv global 3.11.9

python -V

# =========================
# DIRECTORIES (IDEMPOTENT)
# =========================
echo "[6/10] Creating directory structure..."

sudo mkdir -p /opt/saem/models
sudo mkdir -p /opt/saem/config

sudo mkdir -p /opt/nicu_audit/bin
sudo mkdir -p /opt/nicu_audit/data
sudo mkdir -p /opt/nicu_audit/logs
sudo mkdir -p /opt/nicu_audit/config

sudo chown -R $USER:$USER /opt/saem
sudo chown -R $USER:$USER /opt/nicu_audit

# =========================
# VENV (REBUILD SAFE)
# =========================
echo "[7/10] Creating Python environment..."

rm -rf /opt/saem/venv311 || true

python -m venv /opt/saem/venv311

/opt/saem/venv311/bin/pip install --upgrade pip

echo "[deps] Installing Python packages..."

/opt/saem/venv311/bin/pip install \
    numpy==1.26.4 \
    scipy \
    pandas \
    sounddevice

echo "[deps] Installing tflite-runtime..."

/opt/saem/venv311/bin/pip install \
    tflite-runtime==2.14.0 \
    --extra-index-url https://www.piwheels.org/simple

# =========================
# COPY FILES (SAFE)
# =========================
echo "[8/10] Deploying project files..."

cp -r nicu_audit/* /opt/nicu_audit/ || true
cp -r external/* /opt/saem/ || true
cp -r models/* /opt/saem/models/ || true
cp -r bin/* /opt/nicu_audit/bin/ || true

# =========================
# NODE CONFIG
# =========================
echo "[config] Writing node.env..."

cat <<EOF > /opt/saem/config/node.env
NODE_ID=$NODE_ID
ROOM=$ROOM
LOCATION=$LOCATION
EOF

# =========================
# FIFO SERVICE
# =========================
echo "[9/10] Installing FIFO service..."

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

sudo systemctl restart saem-fifo-setup
sleep 2

sudo systemctl restart nicu-audit
sudo systemctl restart saem-loudness
sudo systemctl restart saem-system-monitor

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

echo "Next:"
echo "sudo reboot"
echo "saem-live"
