#!/bin/bash

set -e

PYTHON_VERSION=3.11.9
VENV_PATH=/opt/saem/venv311

echo "[venv] Installing pyenv..."

if [ ! -d "$HOME/.pyenv" ]; then
    curl https://pyenv.run | bash
fi

export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

echo "[venv] Installing Python $PYTHON_VERSION..."
pyenv install -s $PYTHON_VERSION

echo "[venv] Creating venv..."
pyenv virtualenv -f $PYTHON_VERSION saem-env
pyenv activate saem-env

rm -rf $VENV_PATH
python -m venv $VENV_PATH

source $VENV_PATH/bin/activate

pip install --upgrade pip

pip install \
    "numpy<2" \
    scipy \
    pandas \
    sounddevice \
    tflite-runtime

echo "[venv] DONE"
