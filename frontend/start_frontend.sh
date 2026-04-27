#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f "package.json" ]]; then
  echo "package.json not found in $SCRIPT_DIR" >&2
  exit 1
fi

if [[ ! -d "node_modules" ]]; then
  echo "node_modules not found in $SCRIPT_DIR" >&2
  echo "Run npm install first." >&2
  exit 1
fi

echo "Starting frontend from $SCRIPT_DIR"

exec npm start
