#!/bin/bash

ENV_FILE="/opt/saem/config/node.env"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

while true; do

TODAY=$(date +%Y-%m-%d)

# ===============================
# NICU (levels + events)
# ===============================
NICU=$(grep -v '^date' /opt/nicu_audit/data/*${TODAY}*nicu_audit*.csv 2>/dev/null | tail -n 1)

DATE=$(echo "$NICU" | awk -F, '{print $1}')
TIME=$(echo "$NICU" | awk -F, '{print $2}')

LAEQ=$(echo "$NICU" | awk -F, '{print $3}')
EVT=$(echo "$NICU" | awk -F, '{print $(NF-1)}')

# ===============================
# LOUDNESS (perceptual)
# ===============================
LOUD=$(grep -v '^date' /opt/nicu_audit/data/*${TODAY}*perceptual*.csv 2>/dev/null | tail -n 1)

LTL=$(echo "$LOUD" | awk -F, '{print $(NF-2)}')
STL=$(echo "$LOUD" | awk -F, '{print $(NF-1)}')

# ===============================
# SYSTEM MONITOR (NEW PIPE)
# ===============================
if [ -f /tmp/saem_sys.txt ]; then
    SYS=$(cat /tmp/saem_sys.txt)
    CPU=$(echo "$SYS" | cut -d',' -f1)
    TEMP=$(echo "$SYS" | cut -d',' -f2)
else
    CPU="..."
    TEMP="..."
fi

# ===============================
# DISPLAY
# ===============================
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

sleep 10

done
