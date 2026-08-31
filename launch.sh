#!/usr/bin/env sh
# Launch the desk on a public Cloudflare URL, show it, and keep the window
# open so the address stays on screen.
#
# The desk and the tunnel start detached, so closing this window afterwards
# leaves them running.
cd "$(dirname "$0")" || exit 1

if [ ! -x .venv/bin/python ]; then
  echo
  echo "  No .venv here yet. Run ./setup.sh first."
  echo
  printf '  Press Enter to close... '
  read -r _
  exit 1
fi

echo
.venv/bin/python tools/appctl.py launch
RC=$?

echo
[ "$RC" -eq 0 ] || echo "  Launch reported a problem (exit $RC). See var/api.out and var/tunnel.out."

# Only wait when there is a human at a terminal; in a script or a pipe this
# would hang forever.
if [ -t 0 ]; then
  echo
  printf '  Press Enter to close this window (the desk keeps running)... '
  read -r _
fi
exit "$RC"
