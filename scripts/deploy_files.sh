#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[files] Deploying project..."

mkdir -p /opt/nicu_audit
mkdir -p /opt/nicu_audit/logs
mkdir -p /opt/nicu_audit/data
mkdir -p /opt/nicu_audit/meta
mkdir -p /opt/nicu_audit/summary

mkdir -p /opt/saem/models
mkdir -p /opt/saem/config
mkdir -p /opt/saem/LoudnessModel

rsync -av \
  --exclude 'logs/' \
  --exclude 'data/' \
  --exclude 'meta/' \
  --exclude 'summary/' \
  "$REPO_ROOT/nicu_audit/" /opt/nicu_audit/

rsync -av "$REPO_ROOT/models/" /opt/saem/models/

cp "$REPO_ROOT/config/node.env" /opt/saem/config/node.env

echo "[files] Deploying LoudnessModel..."
rsync -av "$REPO_ROOT/external/LoudnessModel/" /opt/saem/LoudnessModel/

echo "[files] Creating runtime files..."

touch /opt/nicu_audit/logs/nicu_audit.log
touch /opt/nicu_audit/logs/system_monitor.log
touch /opt/nicu_audit/logs/loudness.log

chmod +x /opt/nicu_audit/bin/setup_loudness_fifo.sh
chmod +x /opt/nicu_audit/src/saemcclive.sh 2>/dev/null || true

chown -R saem:saem /opt/nicu_audit
chown -R saem:saem /opt/saem

chmod -R 755 /opt/nicu_audit
chmod -R 755 /opt/saem
