#!/usr/bin/env sh
# Tradier Bot desk (Vite dev server) on http://127.0.0.1:5199
# The API must be running too: ../run.sh
cd "$(dirname "$0")" || exit 1
[ -d node_modules ] || { echo "Installing frontend dependencies ..."; npm install; }
npm run dev
