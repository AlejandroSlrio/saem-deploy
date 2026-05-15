#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="/opt/saem/update.log"

echo "=========================================" | tee -a "$LOG"
echo " SAEM UPDATE $(date)" | tee -a "$LOG"
echo "=========================================" | tee -a "$LOG"

cd "$REPO_ROOT"

echo "[update] Pulling latest repo..." | tee -a "$LOG"
git pull | tee -a "$LOG"

echo "[update] Applying RTC update..." | tee -a "$LOG"
bash "$REPO_ROOT/scripts/updates/001_rtc_pi5.sh"

echo "[update] Restarting SAEM services..." | tee -a "$LOG"
systemctl restart saem-system-monitor || true
systemctl restart nicu-audit || true
sleep 5
systemctl restart saem-loudness || true

echo "[update] Status:" | tee -a "$LOG"
systemctl is-active nicu-audit | tee -a "$LOG"
systemctl is-active saem-loudness | tee -a "$LOG"
systemctl is-active saem-system-monitor | tee -a "$LOG"

echo "[update] DONE" | tee -a "$LOG"
