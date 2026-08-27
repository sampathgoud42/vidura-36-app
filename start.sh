#!/usr/bin/env sh
# Start the Tradier Bot (detached). Desk and API share port 8790.
#   ./start.sh          API + built desk
#   ./start.sh --dev    also run the Vite dev server on 5199 (hot reload)
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "No .venv here yet - run ./setup.sh first."; exit 1; }
exec .venv/bin/python tools/appctl.py start "$@"
