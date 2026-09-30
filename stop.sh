#!/usr/bin/env sh
# Stop Vidura: the tunnel first, so vidura36.app never points at a desk that
# is shutting down, then the dev server, then the API.
#
# Bots are NOT stopped: each is a separate process holding positions of its
# own - stop them from the Bot Station. Take-profits rest at the venue and
# keep working while the desk is down; the stop-loss monitor does not (see
# DEPLOY.md, "What stopping does and does not do").
#
# Nor is anything that is not this machine's or not this project's: the web
# app on Cloudflare's edge keeps loading, its sign-in saying the desk is
# offline, and the signal desk's service keeps running on its own task.
#
# Only ever signals processes started from THIS folder, so an unrelated app on
# the machine is never touched.
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "No .venv here yet - nothing to stop."; exit 0; }
exec .venv/bin/python tools/appctl.py stop "$@"
