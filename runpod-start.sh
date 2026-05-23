#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "train" ]]; then
  shift
  exec /opt/lichtfeld-dist/bin/run_lichtfeld.sh "$@"
fi

if [[ "${1:-}" == "lichtfeld" ]]; then
  shift
  exec /opt/lichtfeld-dist/bin/run_lichtfeld.sh "$@"
fi

if [[ "${1:-}" == "version" ]]; then
  echo "LichtFeld upstream revision: $(cat /opt/lichtfeld-upstream-revision.txt 2>/dev/null || echo unknown)"
  /opt/lichtfeld-dist/bin/run_lichtfeld.sh --help || true
  exit 0
fi

exec "$@"
