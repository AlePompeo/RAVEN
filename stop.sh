#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Stops only the server started by install.sh (PID file); never kills by name pattern.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$ROOT/.server.pid"

if [ ! -f "$PIDFILE" ]; then
  echo "No server started by install.sh is recorded (.server.pid not found)."
  exit 0
fi
pid="$(sed -n 1p "$PIDFILE")"
port="$(sed -n 2p "$PIDFILE")"
case "$pid" in ''|*[!0-9]*) echo "ERROR: .server.pid is malformed; delete it." >&2; exit 1 ;; esac
[ "$pid" -gt 1 ] || { echo "ERROR: .server.pid is malformed; not touching it." >&2; exit 1; }

if ! kill -0 "$pid" 2> /dev/null; then
  echo "The server (pid $pid) is not running any more."
  rm -f "$PIDFILE"
  exit 0
fi
# Safety: the PID must still be our uvicorn (guards against a recycled PID).
cmd="$(ps -p "$pid" -o command= 2> /dev/null || true)"
if [ "$cmd" != "$ROOT/.venv/bin/python -m uvicorn --factory backend.bootstrap:build_app --host 127.0.0.1 --port $port" ]; then
  echo "ERROR: pid $pid is not this project's server; not touching it. Delete .server.pid if stale." >&2
  exit 1
fi
kill "$pid"
for _ in $(seq 1 20); do
  kill -0 "$pid" 2> /dev/null || break
  sleep 0.5
done
if kill -0 "$pid" 2> /dev/null; then
  echo "Server did not stop on SIGTERM; sending SIGKILL to pid $pid."
  kill -9 "$pid" 2> /dev/null || true
fi
rm -f "$PIDFILE"
echo "Server stopped."
