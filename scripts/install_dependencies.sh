#!/bin/bash
set -e

echo "[deps] Installing system dependencies..."

apt install -y \
  python3 \
  python3-pip \
  python3-venv \
  git \
  ffmpeg \
  portaudio19-dev \
  alsa-utils \
  sox \
  libsndfile1 \
  curl
