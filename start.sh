#!/usr/bin/env sh
# Start the desk (detached) and publish it at https://vidura36.app
#
#   ./start.sh              API + built desk + the public tunnel
#   ./start.sh --no-tunnel  keep it local on 127.0.0.1:8791 only
#   ./start.sh --dev        also run the Vite dev server on 5199 (hot reload)
#
# The tunnel is ON by default: this project has a NAMED Cloudflare tunnel on
# its own domain, so publishing is how it normally runs. It used to be an
# opt-in flag, which meant this script brought the desk up with no public
# address while still reporting success.
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "No .venv here yet - run ./setup.sh first."; exit 1; }
exec .venv/bin/python tools/appctl.py start "$@"
