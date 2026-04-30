#!/bin/bash
set -e

echo "[venv] Creating virtual environment..."

VENV=/opt/saem/venv311

if [ ! -d "$VENV" ]; then
  python3 -m venv $VENV
fi

source $VENV/bin/activate

pip install --upgrade pip

pip install \
  numpy \
  scipy \
  pandas \
  sounddevice \
  tflite-runtime

deactivate
