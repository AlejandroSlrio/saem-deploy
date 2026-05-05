#!/bin/bash
set -e

echo "[time] Installing HTTPS time sync..."

# Detect repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Copy script
cp "$REPO_ROOT/nicu_audit/scripts/https-time-sync.sh" /usr/local/bin/https-time-sync.sh
chmod +x /usr/local/bin/https-time-sync.sh

# Copy service
cp "$REPO_ROOT/services/https-time-sync.service" /etc/systemd/system/

# Enable service
systemctl daemon-reload
systemctl enable https-time-sync.service
systemctl restart https-time-sync.service

echo "[time] HTTPS time sync installed"
