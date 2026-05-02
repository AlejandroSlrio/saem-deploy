#!/bin/bash

set -e

if [ -z "$1" ]; then
    echo "Usage: ./setup_ssh_access.sh user@host"
    echo "Example: ./setup_ssh_access.sh saem-n3@100.77.121.62"
    exit 1
fi

TARGET="$1"
PUBKEY="$HOME/.ssh/id_ed25519.pub"

if [ ! -f "$PUBKEY" ]; then
    echo "[ERROR] Public key not found: $PUBKEY"
    echo "Create one first with: ssh-keygen -t ed25519"
    exit 1
fi

echo "[ssh] Installing key on $TARGET"

cat "$PUBKEY" | ssh "$TARGET" \
'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'

echo "[ssh] Done. Test with:"
echo "ssh $TARGET"
