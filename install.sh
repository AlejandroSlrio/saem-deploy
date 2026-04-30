#!/bin/bash
set -e

echo "========================================="
echo " SAEM DEPLOYMENT START"
echo "========================================="

# -------------------------
# ROOT CHECK
# -------------------------
if [ "$EUID" -ne 0 ]; then
  echo "Run with: sudo bash install.sh"
  exit 1
fi

# -------------------------
# MOVE TO SCRIPT DIR
# -------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/scripts"

# -------------------------
# SYSTEM UPDATE (SAFE)
# -------------------------
echo "[0/9] Updating system..."
apt update

# -------------------------
# PIPELINE
# -------------------------
echo "[1/9] Dependencies"
bash install_dependencies.sh

echo "[2/9] User setup"
bash setup_user.sh

echo "[3/9] Audio setup"
bash setup_audio.sh

echo "[4/9] Time sync"
bash setup_time_sync.sh

echo "[5/9] Tailscale"
bash setup_tailscale.sh

echo "[6/9] Python environment"
bash setup_venv.sh

echo "[7/9] Deploy files"
bash deploy_files.sh

echo "[8/9] Deploy services"
bash deploy_services.sh

echo "[9/9] Health check"
bash health_check.sh

echo "[runtime] Fixing runtime environment..."

# =========================
# DIRECTORIOS CRÍTICOS
# =========================
mkdir -p /opt/nicu_audit/logs
mkdir -p /opt/nicu_audit/data

# =========================
# LOG FILES (evita crash systemd)
# =========================
touch /opt/nicu_audit/logs/nicu_audit.log
touch /opt/nicu_audit/logs/system_monitor.log
touch /opt/nicu_audit/logs/loudness.log

# =========================
# FIFO (CRÍTICO para loudness)
# =========================
mkfifo /tmp/saem_audio_fifo 2>/dev/null || true
chown saem:saem /tmp/saem_audio_fifo
chmod 660 /tmp/saem_audio_fifo

# =========================
# PERMISOS (CRÍTICO)
# =========================
chown -R saem:saem /opt/saem
chown -R saem:saem /opt/nicu_audit

chmod -R 755 /opt/saem
chmod -R 755 /opt/nicu_audit

echo "[runtime] OK"

echo "========================================="
echo " SAEM DEPLOYMENT COMPLETE"
echo "========================================="

echo ""
echo "Next steps:"
echo "-----------------------------------------"
echo "1) Connect Tailscale:"
echo "   sudo tailscale up"
echo ""
echo "2) Optional reboot:"
echo "   sudo reboot"
echo ""
echo "3) Check logs:"
echo "   tail -f /opt/nicu_audit/logs/nicu_audit.log"
echo "-----------------------------------------"
