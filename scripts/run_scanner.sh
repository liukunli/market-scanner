#!/bin/bash
# Wrapper for launchd (or manual) runs of a scanner entrypoint.
#   Usage: run_scanner.sh run_premarket | run_hourly | run_index_30m
# Loads SLACK_BOT_TOKEN from ~/.config/market-scanner.env, runs the module from
# the repo root, and appends output to ~/Library/Logs/market-scanner/<module>.log.
set -euo pipefail

MODULE="${1:?usage: run_scanner.sh <run_premarket|run_hourly|run_index_30m>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
ENVFILE="$HOME/.config/market-scanner.env"
PY="/usr/bin/python3"
LOGDIR="$HOME/Library/Logs/market-scanner"
mkdir -p "$LOGDIR"

# shellcheck disable=SC1090
[ -f "$ENVFILE" ] && set -a && . "$ENVFILE" && set +a

cd "$REPO"
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') :: scanners.$MODULE ==="
  "$PY" -m "scanners.$MODULE"
  echo "--- exit $? ---"
} >> "$LOGDIR/$MODULE.log" 2>&1
