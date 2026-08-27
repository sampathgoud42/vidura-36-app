#!/usr/bin/env sh
# Print the desk's current public tunnel URL, and nothing else.
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "No .venv here yet - run ./setup.sh first."; exit 1; }
exec .venv/bin/python tools/appctl.py url "$@"
