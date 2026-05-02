#!/bin/bash

set -e

echo "========================================="
echo " SAEM NODE RUNTIME UPDATE"
echo "========================================="

cd ~/saem-deploy
git pull

echo "[update] Deploying project files..."
sudo cp -r nicu_audit/* /opt/nicu_audit/

echo "[update] Deploying services..."
sudo cp services/*.service /etc/systemd/system/

echo "[update] Fixing permissions..."
sudo mkdir -p /home/saem/.ssh
sudo touch /home/saem/.ssh/authorized_keys
sudo chmod 700 /home/saem/.ssh
sudo chmod 600 /home/saem/.ssh/authorized_keys
sudo chown -R saem:saem /home/saem/.ssh

sudo chmod +x /opt/nicu_audit/scripts/https-time-sync.sh 2>/dev/null || true
sudo chmod +x /opt/nicu_audit/bin/saemcclive.sh 2>/dev/null || true

echo "[update] Reloading systemd..."
sudo systemctl daemon-reload

sudo systemctl enable https-time-sync.service 2>/dev/null || true
sudo systemctl restart https-time-sync.service 2>/dev/null || true

sudo systemctl restart nicu-audit
sudo systemctl restart saem-loudness
sudo systemctl restart saem-system-monitor

echo "========================================="
echo " STATUS"
echo "========================================="
systemctl is-active nicu-audit || true
systemctl is-active saem-loudness || true
systemctl is-active saem-system-monitor || true
systemctl is-active https-time-sync.service || true

echo "Done."
