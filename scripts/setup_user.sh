#!/bin/bash
set -e

echo "[user] Setting up saem user..."

id -u saem >/dev/null 2>&1 || sudo useradd -m -s /bin/bash saem
sudo usermod -aG audio saem
