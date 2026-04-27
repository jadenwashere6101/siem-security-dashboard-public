#!/bin/bash

SIEM_BASE_URL="${SIEM_BASE_URL:-http://127.0.0.1:5050}"
NUM_IPS="${NUM_IPS:-15}"   # change this to control how many alerts you want

echo "Generating $NUM_IPS random attack sources using $SIEM_BASE_URL ..."

for i in $(seq 1 $NUM_IPS); do
  # Generate random IP
  ip="$((RANDOM%256)).$((RANDOM%256)).$((RANDOM%256)).$((RANDOM%256))"

  echo "Simulating attack from $ip"

  python3 simulate_attacks.py --failed-logins 10 --ip "$ip"

  # small delay so DB + detection stays clean
  sleep 1

  curl -s -X POST "$SIEM_BASE_URL/alerts/generate/failed-logins"

  echo ""
done

echo "----------------------------------"
echo "Final Alerts:"
curl -s "$SIEM_BASE_URL/alerts"
echo ""
