#!/bin/bash

URLS=(
  "https://www.google.com"
  "https://www.cloudflare.com"
  "https://www.github.com"
)

for i in {1..10}; do
  for url in "${URLS[@]}"; do
    DATE_HDR=$(curl -k -fsI --max-time 10 "$url" 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /^date:/{sub(/\r$/,""); print substr($0,7)}')
    if [ -n "$DATE_HDR" ]; then
      /usr/bin/date -u -s "$DATE_HDR" >/dev/null 2>&1
      exit 0
    fi
  done
  sleep 3
done

exit 1
