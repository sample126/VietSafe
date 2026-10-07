#!/usr/bin/env sh
# Chạy VietSafe trên macOS / Linux:  ./scripts/start.sh [cổng]
set -e
cd "$(dirname "$0")/../backend"
exec python3 -m vietsafe --port "${1:-8765}"
