#!/bin/bash
set -e

LOG="/opt/saem/update.log"
TARGET="/opt/nicu_audit/src/nicu_audit_levels_v5_1_3.py"

INTERVAL="${THIRD_OCTAVE_INTERVAL_S:-1}"

echo "=========================================" | tee -a "$LOG"
echo " SAEM UPDATE: Set third-octave interval $(date)" | tee -a "$LOG"
echo "=========================================" | tee -a "$LOG"

echo "[info] Target file: $TARGET" | tee -a "$LOG"
echo "[info] third_octave_interval_s=$INTERVAL" | tee -a "$LOG"

if [ ! -f "$TARGET" ]; then
  echo "[ERROR] Target file not found: $TARGET" | tee -a "$LOG"
  exit 1
fi

if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] THIRD_OCTAVE_INTERVAL_S must be an integer." | tee -a "$LOG"
  exit 1
fi

BACKUP="${TARGET}.backup_third_octave_$(date +%Y%m%d_%H%M%S)"
cp "$TARGET" "$BACKUP"
echo "[backup] $BACKUP" | tee -a "$LOG"

sed -i -E "s|\"third_octave_interval_s\": *[0-9]+,|\"third_octave_interval_s\": ${INTERVAL},|g" "$TARGET"

echo "[check] Current setting:" | tee -a "$LOG"
grep '"third_octave_interval_s"' "$TARGET" | tee -a "$LOG"

echo "[done] Third-octave interval updated." | tee -a "$LOG"
echo "[note] update_node_runtime.sh will restart nicu-audit after this update." | tee -a "$LOG"
