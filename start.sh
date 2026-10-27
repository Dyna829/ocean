#!/usr/bin/env bash
# One command: install dependencies, build the console, seed demo data, start the app.
#
#   ./start.sh                 # http://127.0.0.1:8000
#   PORT=8080 ./start.sh       # different port
#   DB_PATH=data/large.db ./start.sh   # serve the 100k-row dataset
#   ./start.sh --reset         # wipe and reseed the demo data
set -euo pipefail

cd "$(dirname "$0")"

export PORT="${PORT:-8000}"
export DB_PATH="${DB_PATH:-$PWD/data/app.db}"
PYTHON_BIN="${PYTHON:-python3}"
SEED_ARGS=()

for argument in "$@"; do
  case "$argument" in
    --reset) SEED_ARGS+=(--reset) ;;
    *) echo "Unknown argument: $argument" >&2; exit 2 ;;
  esac
done

if [ ! -d .venv ]; then
  echo "==> Creating Python virtual environment"
  "$PYTHON_BIN" -m venv .venv
fi

echo "==> Installing Python dependencies"
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt

if [ ! -d web/node_modules ]; then
  echo "==> Installing web dependencies"
  if [ -f web/package-lock.json ]; then
    (cd web && npm ci --no-audit --no-fund --loglevel=error)
  else
    (cd web && npm install --no-audit --no-fund --loglevel=error)
  fi
fi

echo "==> Building the web console"
(cd web && npm run build --silent)

echo "==> Initialising demo data at $DB_PATH"
if [ "${#SEED_ARGS[@]}" -gt 0 ]; then
  .venv/bin/python -m app.seed "${SEED_ARGS[@]}"
else
  .venv/bin/python -m app.seed
fi

echo "==> Certificate Admin Console: http://127.0.0.1:${PORT}"
exec .venv/bin/python -m uvicorn app.asgi:app --host 127.0.0.1 --port "$PORT" --no-access-log
