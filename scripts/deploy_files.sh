#!/bin/bash

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[files] Deploying project..."

sudo mkdir -p /opt/nicu_audit
sudo rsync -av --delete "$REPO_ROOT/nicu_audit/" /opt/nicu_audit/

sudo mkdir -p /opt/saem/models
sudo rsync -av "$REPO_ROOT/models/" /opt/saem/models/

echo "[files] Deploying LoudnessModel..."

sudo mkdir -p /opt/saem/LoudnessModel
sudo rsync -av "$REPO_ROOT/external/LoudnessModel/" /opt/saem/LoudnessModel/
