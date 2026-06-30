#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# fileShare — local dev runner.
# First run sets up a self-contained Python environment (no sudo needed),
# installs dependencies, then starts the server. Re-runs just start it.
#
#   ./run.sh            # serve on http://127.0.0.1:8000 (password: test)
#   PORT=9000 ./run.sh  # use a different port
#   PHONE=1 ./run.sh    # also expose on your LAN so a phone can connect
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
PY="$VENV/bin/python"

# 1. Create the virtual environment (fall back to a pip-less venv if the
#    python3-venv package's ensurepip isn't available on this machine).
if [ ! -x "$PY" ]; then
  echo "→ Creating virtual environment…"
  python3 -m venv "$VENV" >/dev/null 2>&1 || python3 -m venv --without-pip "$VENV"
fi

# 2. Make sure pip exists inside the venv (bootstrap it if needed).
if [ ! -x "$VENV/bin/pip" ]; then
  echo "→ Bootstrapping pip…"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/fileshare-get-pip.py
  "$PY" /tmp/fileshare-get-pip.py -q
  rm -f /tmp/fileshare-get-pip.py
fi

# 3. Install dependencies once (skip if Flask already imports).
if ! "$PY" -c "import flask, waitress" >/dev/null 2>&1; then
  echo "→ Installing dependencies…"
  "$VENV/bin/pip" install -q -r requirements.txt
fi

# 4. Sensible local defaults (override by exporting before running).
export FILESHARE_PASSWORD="${FILESHARE_PASSWORD:-test}"
export FILESHARE_PORT="${PORT:-8000}"
if [ "${PHONE:-0}" = "1" ]; then
  export FILESHARE_HOST="0.0.0.0"
  IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "→ Phone access: http://${IP:-<this-pc-ip>}:${FILESHARE_PORT}"
else
  export FILESHARE_HOST="${FILESHARE_HOST:-127.0.0.1}"
fi

echo "→ Open http://127.0.0.1:${FILESHARE_PORT}   (password: ${FILESHARE_PASSWORD})"
echo "→ Press Ctrl+C to stop."
exec "$PY" app.py
