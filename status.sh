#!/usr/bin/env sh
# What is running, where the data lives, and whether this copy is live.
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "No .venv here yet - run ./setup.sh first."; exit 1; }
exec .venv/bin/python tools/appctl.py status "$@"
