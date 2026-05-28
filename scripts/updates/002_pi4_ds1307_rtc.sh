#!/bin/bash
set -e

LOG="/opt/saem/update.log"
CONFIG="/boot/firmware/config.txt"
OVERLAY_LINE="dtoverlay=i2c-rtc,ds1307"

echo "=========================================" | tee -a "$LOG"
echo " SAEM UPDATE: Pi4 DS1307 RTC $(date)" | tee -a "$LOG"
echo "=========================================" | tee -a "$LOG"

MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo unknown)"
echo "[info] Model: $MODEL" | tee -a "$LOG"

if ! echo "$MODEL" | grep -q "Raspberry Pi 4"; then
  echo "[skip] Not Raspberry Pi 4. Skipping DS1307 update." | tee -a "$LOG"
  exit 0
fi

echo "[1/7] Installing packages..." | tee -a "$LOG"
apt update
apt install -y i2c-tools util-linux-extra

echo "[2/7] Checking I2C..." | tee -a "$LOG"
if [ ! -e /dev/i2c-1 ]; then
  echo "[ERROR] /dev/i2c-1 not found. Enable I2C first." | tee -a "$LOG"
  exit 1
fi

echo "[3/7] Checking RTC presence on I2C..." | tee -a "$LOG"
I2C_OUT="$(i2cdetect -y 1)"
echo "$I2C_OUT" | tee -a "$LOG"

if ! echo "$I2C_OUT" | grep -Eq "68|UU"; then
  echo "[ERROR] DS1307 not detected at 0x68." | tee -a "$LOG"
  echo "[hint] Check battery, HAT orientation, SDA/SCL, and power." | tee -a "$LOG"
  exit 1
fi

echo "[4/7] Patching config.txt..." | tee -a "$LOG"
if ! grep -q "^${OVERLAY_LINE}$" "$CONFIG"; then
  BACKUP="${CONFIG}.backup_$(date +%Y%m%d_%H%M%S)"
  cp "$CONFIG" "$BACKUP"
  echo "[backup] $BACKUP" | tee -a "$LOG"

  {
    echo ""
    echo "# SAEM external RTC DS1307 for Raspberry Pi 4"
    echo "$OVERLAY_LINE"
  } >> "$CONFIG"

  echo "[ok] Added: $OVERLAY_LINE" | tee -a "$LOG"
else
  echo "[ok] Overlay already present." | tee -a "$LOG"
fi

echo "[5/7] Removing fake-hwclock..." | tee -a "$LOG"
apt purge -y fake-hwclock || true
systemctl disable fake-hwclock 2>/dev/null || true

echo "[6/7] RTC status..." | tee -a "$LOG"
ls -l /dev/rtc* 2>/dev/null | tee -a "$LOG" || true
cat /sys/class/rtc/rtc0/name 2>/dev/null | tee -a "$LOG" || true

echo "[7/7] Final note..." | tee -a "$LOG"
echo "If this is the first time applying the overlay, reboot is required." | tee -a "$LOG"
echo "After reboot run:" | tee -a "$LOG"
echo "  sudo hwclock -w" | tee -a "$LOG"
echo "  sudo hwclock -r" | tee -a "$LOG"
echo "[done] Pi4 DS1307 update complete." | tee -a "$LOG"
