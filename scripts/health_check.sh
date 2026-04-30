#!/bin/bash

echo "=== SAEM STATUS ==="

systemctl is-active nicu-audit.service
systemctl is-active saem-loudness.service
systemctl is-active saem-system-monitor.service

echo ""
echo "CPU:"
top -bn1 | grep "Cpu(s)"

echo ""
echo "Audio device:"
arecord -l
