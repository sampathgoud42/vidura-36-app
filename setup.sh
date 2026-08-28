#!/usr/bin/env sh
# One-time setup on a fresh machine. Uses the SYSTEM python: this is the
# step that CREATES the virtualenv, so it cannot use one.
cd "$(dirname "$0")" || exit 1
PY=$(command -v python3 || command -v python) || {
  echo "Python 3.12+ is required and was not found on PATH."; exit 1; }
exec "$PY" tools/setup.py "$@"
