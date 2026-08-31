#!/usr/bin/env sh
# Stop the Tradier Bot. Only ever signals processes started from THIS
# folder, so an unrelated app on the machine is never touched.
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "No .venv here yet - nothing to stop."; exit 0; }
exec .venv/bin/python tools/appctl.py stop "$@"
