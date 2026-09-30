#!/usr/bin/env sh
# Start Vidura - everything it needs, in order - and publish it at
# https://vidura36.app
#
#   ./start.sh               set up a fresh copy, install what changed, build
#                            the web app if it is out of date, start the API,
#                            open the tunnel, and put a new build on
#                            Cloudflare's edge once the edge has been deployed
#                            (TUNNEL.md)
#   ./start.sh --restart     stop everything first, then start it again
#   ./start.sh --no-tunnel   keep it on this machine only (127.0.0.1:8791)
#   ./start.sh --dev         also run the Vite dev server on 5199 (hot reload)
#
# It also says whether the signal desk's service is answering: Super Signals
# and the best pair read from it, and it runs from a project of its own.
#
# ./stop.sh takes it all down. Status, the public URL and the audit are one
# command each through tools/ - see README.md.
cd "$(dirname "$0")" || exit 1

if [ ! -x .venv/bin/python ]; then
  echo
  echo "  First start on this machine - setting Vidura up. This takes a few minutes."
  echo
  PY=$(command -v python3 || command -v python) || {
    echo "  Python 3.12+ is required and was not found on PATH."; exit 1; }
  # The system Python: this is the step that creates the virtualenv.
  "$PY" tools/setup.py || exit 1
fi

exec .venv/bin/python tools/appctl.py start "$@"
