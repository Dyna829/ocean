#!/usr/bin/env bash
# Verification: acceptance suites A1-A7 (pytest) plus the web type check.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON:-python3}"

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi

echo "==> Installing verification dependencies"
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt

echo "==> Running the test suite (acceptance A1-A7 + logging)"
.venv/bin/python -m pytest tests -q

if [ ! -d web/node_modules ]; then
  echo "==> Installing web dependencies"
  (cd web && npm install --no-audit --no-fund --loglevel=error)
fi

echo "==> Type-checking the web console"
(cd web && npm run typecheck --silent)

echo "==> All checks passed"
