#!/usr/bin/env bash
set -e

FIFO="/tmp/saem_loudness_fifo"
USER="saem"
GROUP="saem"

echo "[FIFO] Setting up loudness FIFO at $FIFO"

# Eliminar si existe pero no es FIFO
if [ -e "$FIFO" ] && [ ! -p "$FIFO" ]; then
    echo "[FIFO] Removing invalid file"
    rm -f "$FIFO"
fi

# Crear FIFO si no existe
if [ ! -p "$FIFO" ]; then
    echo "[FIFO] Creating FIFO"
    mkfifo "$FIFO"
fi

# Asignar ownership
chown "$USER:$GROUP" "$FIFO"

# Permisos restringidos (rw para owner/group)
chmod 660 "$FIFO"

echo "[FIFO] Ready"
