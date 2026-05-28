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
sudo apt install -y git 

echo "[2/5] Configuring eduroam with NetworkManager..."

sudo nmcli connection delete eduroam 2>/dev/null || true

sudo nmcli connection add \
  type wifi \
  ifname wlan0 \
  con-name eduroam \
  ssid eduroam

sudo nmcli connection modify eduroam \
  wifi-sec.key-mgmt wpa-eap \
  802-1x.eap peap \
  802-1x.phase2-auth mschapv2 \
  802-1x.identity "$EDUROAM_USER" \
  802-1x.password "$EDUROAM_PASS" \
  802-1x.anonymous-identity "anonymous@universityofgalway.ie" \
  connection.autoconnect yes

sudo nmcli connection up eduroam

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
