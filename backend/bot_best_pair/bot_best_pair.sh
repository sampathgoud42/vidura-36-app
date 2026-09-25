#!/usr/bin/env sh
# Start the best-pairs bot: the daily report's best ticker + signal pairs,
# auto-traded on Tradier by a process of its own. Runs until Ctrl-C.
#
#   ./backend/bot_best_pair/bot_best_pair.sh           trade
#   ./backend/bot_best_pair/bot_best_pair.sh --check   check the setup, trade nothing
#
# Settings: bot_best_pair.env beside this script. The database, the master
# key and paper-only come from the project .env, shared with the desk, so the
# bot and the desk see the same positions and never trade the same signal.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)" || exit 1
cd "$ROOT" || exit 1
[ -x .venv/bin/python ] || { echo "No .venv here yet - run ./setup.sh first."; exit 1; }
PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}" exec .venv/bin/python -m bot_best_pair "$@"
