#!/bin/bash
set -e

echo "[files] Deploying project..."

mkdir -p /opt/nicu_audit
mkdir -p /opt/saem/models
mkdir -p /opt/saem/config
cp ../config/node.env /opt/saem/config/


rsync -av \
  --exclude 'logs/*' \
  --exclude 'data/*' \
  --exclude 'meta/*' \
  --exclude 'summary/*' \
  --exclude '*_backup.py' \
  ../nicu_audit/ /opt/nicu_audit/
rsync -av ../models/ /opt/saem/models/

chown -R saem:saem /opt/nicu_audit
chown -R saem:saem /opt/saem

chmod +x /opt/nicu_audit/bin/setup_loudness_fifo.sh
chmod +x /opt/nicu_audit/src/saemcclive.sh


