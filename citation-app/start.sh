#!/bin/bash
# Reliable startup: kill any process on port 5000 before launching Flask
echo "Clearing port 5000..."
kill -9 $(ss -tlnp 'sport = :5000' 2>/dev/null | awk 'NR>1{print $NF}' | grep -oP 'pid=\K[0-9]+') 2>/dev/null || true
sleep 1
echo "Starting Flask..."
cd "$(dirname "$0")"
exec python flask_app.py
