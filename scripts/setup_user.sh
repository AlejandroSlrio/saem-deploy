#!/bin/bash
set -e

echo "[user] Setting up saem user..."

id saem >/dev/null 2>&1 || useradd -m -s /bin/bash saem

usermod -aG audio saem
