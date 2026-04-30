#!/bin/bash
set -e

echo "[tailscale] Installing..."

if ! command -v tailscale &> /dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

systemctl enable tailscaled
systemctl start tailscaled

echo "👉 Run: sudo tailscale up"
