#!/bin/bash

while true; do

TODAY=$(date +%Y-%m-%d)

NICU=$(grep -v '^date' /opt/nicu_audit/data/*${TODAY}*nicu_audit*.csv 2>/dev/null | tail -n 1)
LOUD=$(grep -v '^date' /opt/nicu_audit/data/*${TODAY}*perceptual*.csv 2>/dev/null | tail -n 1)
SYS=$(grep -v '^date' /opt/nicu_audit/data/system_monitor.csv 2>/dev/null | tail -n 1)

DATE=$(echo "$NICU" | awk -F, '{print $1}')
TIME=$(echo "$NICU" | awk -F, '{print $2}')

LAEQ=$(echo "$NICU" | awk -F, '{print $3}')
EVT=$(echo "$NICU" | awk -F, '{print $(NF-1)}')

LTL=$(echo "$LOUD" | awk -F, '{print $(NF-2)}')
STL=$(echo "$LOUD" | awk -F, '{print $(NF-1)}')

CPU=$(echo "$SYS" | awk -F, '{print $3}')
TEMP=$(echo "$SYS" | awk -F, '{print $4}')

clear
echo "==============================="
echo "       SAEMCC LIVE"
echo "==============================="
echo ""
echo "Time : ${DATE} ${TIME}"
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
