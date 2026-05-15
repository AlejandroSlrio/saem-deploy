#!/bin/bash
set -e

LOG="/opt/saem/update.log"
CONFIG="/boot/firmware/config.txt"

echo "=========================================" | tee -a "$LOG"
echo "[RTC UPDATE] $(date)" | tee -a "$LOG"
echo "=========================================" | tee -a "$LOG"

echo "[1/7] Installing RTC tools..." | tee -a "$LOG"
apt update
apt install -y util-linux-extra raspi-utils-core

echo "[2/7] Checking RTC..." | tee -a "$LOG"
if [ ! -e /dev/rtc0 ]; then
  echo "[ERROR] /dev/rtc0 not found. Is the RTC battery installed?" | tee -a "$LOG"
  exit 1
fi

echo "[3/7] Writing system time to RTC..." | tee -a "$LOG"
hwclock -w || true
hwclock -r | tee -a "$LOG"

echo "[4/7] Enabling RTC battery charging..." | tee -a "$LOG"

if ! grep -q "^dtparam=rtc_bbat_vchg=3000000" "$CONFIG"; then
  cp "$CONFIG" "${CONFIG}.backup_$(date +%Y%m%d_%H%M%S)"
  echo "" >> "$CONFIG"
  echo "# SAEM RTC battery charging" >> "$CONFIG"
  echo "dtparam=rtc_bbat_vchg=3000000" >> "$CONFIG"
else
  echo "[OK] RTC charging config already present" | tee -a "$LOG"
fi

echo "[5/7] Checking charging voltage..." | tee -a "$LOG"
grep . /sys/class/rtc/rtc0/charging_voltage* 2>/dev/null | tee -a "$LOG" || true

echo "[6/7] Patching EEPROM wake settings..." | tee -a "$LOG"

TMP_EEPROM="/tmp/saem-eeprom.conf"
rpi-eeprom-config > "$TMP_EEPROM"

if ! grep -q "^POWER_OFF_ON_HALT=1" "$TMP_EEPROM"; then
  echo "POWER_OFF_ON_HALT=1" >> "$TMP_EEPROM"
fi

if ! grep -q "^WAKE_ON_GPIO=0" "$TMP_EEPROM"; then
  echo "WAKE_ON_GPIO=0" >> "$TMP_EEPROM"
fi

rpi-eeprom-config --apply "$TMP_EEPROM" || {
  echo "[WARN] EEPROM apply failed. Manual edit may be required." | tee -a "$LOG"
}

echo "[7/7] RTC update complete." | tee -a "$LOG"
echo "Reboot recommended." | tee -a "$LOG"
