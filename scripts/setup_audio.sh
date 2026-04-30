#!/bin/bash
set -e

echo "[audio] Verifying audio device..."

arecord -l || echo "No audio device detected"
