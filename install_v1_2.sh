#!/bin/bash

set -e

echo "========================================="
echo " SAEM INSTALLER v1.2 (PYENV STABLE)"
echo "========================================="

# =========================
# CONFIG
# =========================
read -p "Enter NODE_ID (e.g. saem-n3): " NODE_ID
read -p "Enter ROOM (e.g. room-3): " ROOM
read -p "Enter LOCATION (e.g. ot-3): " LOCATION

echo "[config] Using:"
echo "NODE_ID=$NODE_ID"
echo "ROOM=$ROOM"
echo "LOCATION=$LOCATION"

# =========================
# UPDATE
# =========================
echo "[0/9] Updating system..."
sudo apt update

# =========================
# DEPENDENCIES
# =========================
echo "[1/9] Installing dependencies..."

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
# USER SETUP
# =========================
echo "[2/9] User setup..."
sudo usermod -aG audio $USER

# =========================
# PYENV INSTALL
# =========================
echo "[3/9] Installing pyenv..."

if [ ! -d "$HOME/.pyenv" ]; then
    curl https://pyenv.run | bash
fi

export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"

# persist pyenv
grep -q 'pyenv init' ~/.bashrc || echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.bashrc
grep -q 'pyenv init' ~/.bashrc || echo 'eval "$(pyenv init -)"' >> ~/.bashrc

# =========================
# PYTHON 3.11
# =========================
echo "[4/9] Installing Python 3.11..."

pyenv install -s 3.11.9
pyenv global 3.11.9

python -V

# =========================
# FOLDERS
# =========================
echo "[5/9] Creating folders..."

sudo mkdir -p /opt/saem
sudo mkdir -p /opt/nicu_audit

sudo chown -R $USER:$USER /opt/saem
sudo chown -R $USER:$USER /opt/nicu_audit

# =========================
# VENV
# =========================
echo "[6/9] Creating venv..."

python -m venv /opt/saem/venv311

# upgrade pip
/opt/saem/venv311/bin/pip install --upgrade pip

# install deps
echo "[deps] Installing Python packages..."

/opt/saem/venv311/bin/pip install \
    "numpy<2" \
    scipy \
    pandas \
    sounddevice \
    tflite-runtime

# =========================
# COPY FILES
# =========================
echo "[7/9] Copying system files..."

cp -r nicu_audit/* /opt/nicu_audit/
cp -r saem/* /opt/saem/

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
# FIFO
# =========================
echo "[8/9] Creating FIFO..."

rm -f /tmp/saem_loudness_fifo
mkfifo /tmp/saem_loudness_fifo
chmod 666 /tmp/saem_loudness_fifo

# =========================
# SERVICES
# =========================
echo "[9/9] Installing services..."

sudo cp systemd/*.service /etc/systemd/system/

sudo systemctl daemon-reload

sudo systemctl enable nicu-audit
sudo systemctl enable saem-loudness
sudo systemctl enable saem-system-monitor

sudo systemctl start nicu-audit
sudo systemctl start saem-loudness
sudo systemctl start saem-system-monitor

# =========================
# DONE
# =========================
echo "========================================="
echo " SAEM DEPLOYMENT COMPLETE"
echo "========================================="

echo "Next steps:"
echo "-----------------------------------------"
echo "1) Reboot recommended:"
echo "   sudo reboot"
echo ""
echo "2) After reboot:"
echo "   saem-live"
echo ""
echo "3) Check logs:"
echo "   journalctl -u nicu-audit -f"
echo "   journalctl -u saem-loudness -f"
