#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="/opt/saem/update.log"

UPDATE_NAME="${1:-}"

echo "=========================================" | tee -a "$LOG"
echo " SAEM UPDATE $(date)" | tee -a "$LOG"
echo "=========================================" | tee -a "$LOG"

cd "$REPO_ROOT"

echo "[update] Pulling latest repo..." | tee -a "$LOG"
git pull | tee -a "$LOG"

if [ -z "$UPDATE_NAME" ]; then
  echo "[ERROR] No update specified." | tee -a "$LOG"
  echo "" | tee -a "$LOG"
  echo "Usage:" | tee -a "$LOG"
  echo "  sudo bash scripts/update_node_runtime.sh <update_name>" | tee -a "$LOG"
  echo "" | tee -a "$LOG"
  echo "Available updates:" | tee -a "$LOG"

  if ls "$REPO_ROOT"/scripts/updates/*.sh >/dev/null 2>&1; then
    ls "$REPO_ROOT"/scripts/updates/*.sh | xargs -n1 basename | sed 's/.sh$//' | tee -a "$LOG"
  else
    echo "  No updates found in scripts/updates/" | tee -a "$LOG"
  fi

  exit 1
fi

UPDATE_SCRIPT="$REPO_ROOT/scripts/updates/${UPDATE_NAME}.sh"

if [ ! -f "$UPDATE_SCRIPT" ]; then
  echo "[ERROR] Update not found: $UPDATE_NAME" | tee -a "$LOG"
  echo "" | tee -a "$LOG"
  echo "Available updates:" | tee -a "$LOG"

  if ls "$REPO_ROOT"/scripts/updates/*.sh >/dev/null 2>&1; then
    ls "$REPO_ROOT"/scripts/updates/*.sh | xargs -n1 basename | sed 's/.sh$//' | tee -a "$LOG"
  else
    echo "  No updates found in scripts/updates/" | tee -a "$LOG"
  fi

  exit 1
fi

echo "[update] Running selected update: $UPDATE_NAME" | tee -a "$LOG"
bash "$UPDATE_SCRIPT" | tee -a "$LOG"

echo "[update] Restarting SAEM services..." | tee -a "$LOG"

systemctl restart saem-system-monitor || true
systemctl restart nicu-audit || true

if systemctl is-enabled saem-loudness >/dev/null 2>&1; then
    sleep 5
    systemctl restart saem-loudness || true
else
    echo "[update] saem-loudness disabled, skipping..." | tee -a "$LOG"
fi

echo "[update] Status:" | tee -a "$LOG"
echo "nicu-audit:" | tee -a "$LOG"
systemctl is-active nicu-audit | tee -a "$LOG" || true

echo "saem-loudness:" | tee -a "$LOG"

if systemctl is-enabled saem-loudness >/dev/null 2>&1; then
    systemctl is-active saem-loudness | tee -a "$LOG" || true
else
    echo "disabled" | tee -a "$LOG"
fi

echo "saem-system-monitor:" | tee -a "$LOG"
systemctl is-active saem-system-monitor | tee -a "$LOG" || true

echo "[update] DONE" | tee -a "$LOG"
