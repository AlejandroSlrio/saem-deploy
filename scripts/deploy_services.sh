#!/bin/bash
set -e

echo "[services] Installing services..."

cp ../services/*.service /etc/systemd/system/

systemctl daemon-reexec
systemctl daemon-reload

systemctl enable saem-fifo-setup.service
systemctl enable nicu-audit.service
systemctl enable saem-loudness.service
systemctl enable saem-system-monitor.service

systemctl restart saem-fifo-setup.service
systemctl restart saem-loudness.service
systemctl restart nicu-audit.service
systemctl restart saem-system-monitor.service
