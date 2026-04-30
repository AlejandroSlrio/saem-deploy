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

sudo apt install -y \
  build-essential \
  libssl-dev \
  zlib1g-dev \
  libbz2-dev \
  libreadline-dev \
  libsqlite3-dev \
  libffi-dev \
  libncursesw5-dev \
  xz-utils \
  tk-dev \
  libxml2-dev \
  libxmlsec1-dev \
  liblzma-dev
