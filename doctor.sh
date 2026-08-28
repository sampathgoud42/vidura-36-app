#!/usr/bin/env sh
# Prove this copy is self-contained: paths, sources, data, desk.
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then exec .venv/bin/python tools/doctor.py "$@"; fi
PY=$(command -v python3 || command -v python) || { echo "python not found"; exit 1; }
exec "$PY" tools/doctor.py "$@"
