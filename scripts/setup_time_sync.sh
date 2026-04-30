#!/bin/bash
set -e

echo "[time] Installing HTTPS time sync..."

cp ../scripts/https-time-sync.sh /usr/local/bin/
chmod +x /usr/local/bin/https-time-sync.sh

cp ../services/https-time-sync.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable https-time-sync.service
systemctl restart https-time-sync.service
