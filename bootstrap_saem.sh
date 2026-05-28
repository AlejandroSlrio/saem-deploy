#!/bin/bash
set -e

echo "========================================="
echo " SAEM BOOTSTRAP"
echo "========================================="

read -p "Eduroam username: " EDUROAM_USER
read -s -p "Eduroam password: " EDUROAM_PASS
echo ""

read -p "TAILSCALE_AUTHKEY: " TAILSCALE_AUTHKEY
read -p "SSH_PUB_KEY: " SSH_PUB_KEY
read -p "NODE_ID, e.g. saem-n8: " NODE_ID
read -p "ROOM, e.g. nicu: " ROOM
read -p "LOCATION, e.g. inc-2: " LOCATION

echo "[1/5] Installing prerequisites..."
sudo apt update
sudo apt install -y git python3-dbus

echo "[2/5] Installing eduroam..."
python3 external/eduroam/eduroam-linux-UoG.py \
  --username "$EDUROAM_USER" \
  --password "$EDUROAM_PASS" \
  --silent

echo "[3/5] Checking internet..."
ping -c 3 github.com

echo "[4/5] Updating repo..."
cd "$(dirname "$0")"
git pull || true

echo "[5/5] Running SAEM installer..."
sudo \
TAILSCALE_AUTHKEY="$TAILSCALE_AUTHKEY" \
SSH_PUB_KEY="$SSH_PUB_KEY" \
NODE_ID="$NODE_ID" \
ROOM="$ROOM" \
LOCATION="$LOCATION" \
bash install_stable.sh

echo "========================================="
echo " BOOTSTRAP COMPLETE"
echo " Reboot recommended: sudo reboot"
echo "========================================="
