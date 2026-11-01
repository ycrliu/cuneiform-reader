#!/usr/bin/env bash
# Serve the reader locally (the pages fetch JSON, so they need HTTP, not file://).
cd "$(dirname "$0")/.."
port="${1:-8000}"
echo "Cuneiform Reader at http://localhost:${port}/  (Ctrl-C to stop)"
exec python3 -m http.server "$port" --bind 127.0.0.1
