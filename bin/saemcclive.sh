#!/bin/bash

ENV_FILE="/opt/saem/config/node.env"
DATA_DIR="/opt/nicu_audit/data"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

while true; do

TODAY=$(date +%Y-%m-%d)

LEVELS_FILE=$(ls "$DATA_DIR"/*"${TODAY}"*_levels_1s.csv 2>/dev/null | tail -n 1)
LOUD_FILE=$(ls "$DATA_DIR"/*"${TODAY}"*_loudness.csv 2>/dev/null | tail -n 1)

NICU=""
LOUD=""

if [ -n "$LEVELS_FILE" ] && [ -f "$LEVELS_FILE" ]; then
    NICU=$(tail -n 1 "$LEVELS_FILE")
fi

if [ -n "$LOUD_FILE" ] && [ -f "$LOUD_FILE" ]; then
    LOUD=$(tail -n 1 "$LOUD_FILE")
fi

DATE=$(echo "$NICU" | cut -d',' -f1)
TIME=$(echo "$NICU" | cut -d',' -f2)
LAEQ=$(echo "$NICU" | cut -d',' -f3)
EVT=$(echo "$NICU" | awk -F',' '{print $(NF-1)}')

LTL=$(echo "$LOUD" | cut -d',' -f6)
STL=$(echo "$LOUD" | cut -d',' -f7)

if [ -f /tmp/saem_sys.txt ]; then
    SYS=$(cat /tmp/saem_sys.txt)
    CPU=$(echo "$SYS" | cut -d',' -f1)
    TEMP=$(echo "$SYS" | cut -d',' -f2)
else
    CPU="..."
    TEMP="..."
fi

clear
echo "==============================="
echo "       SAEMCC LIVE"
echo "Node : ${NODE_ID:-unknown}"
echo "Loc  : ${LOCATION:-unknown}"
echo "==============================="
echo ""
echo "Time : ${DATE:-...} ${TIME:-...}"
echo ""
echo "LAeq : ${LAEQ:-...} dB"
echo "Event: ${EVT:-...}"
echo ""
echo "STL  : ${STL:-...} phon"
echo "LTL  : ${LTL:-...} phon"
echo ""
echo "CPU  : ${CPU:-...}"
echo "Temp : ${TEMP:-...} °C"
echo ""

sleep 2

done
