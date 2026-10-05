#!/usr/bin/env bash
set -euo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -f "$BASE/.env" ]]; then set -a; source "$BASE/.env"; set +a; fi
DATA=${WORKSHOP_DATA:-$BASE/runtime}
[[ -f "$DATA/service.pid" ]] || { echo 'No service PID recorded.'; exit 0; }
pid=$(cat "$DATA/service.pid")
[[ "$pid" =~ ^[0-9]+$ ]] || { echo 'Invalid PID'; exit 1; }
if [[ -f "/proc/$pid/cmdline" ]]; then
 cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline")
 if [[ "$cmd" == *'uvicorn service:app'* && "$cmd" == *"$BASE"* ]]; then kill -TERM "$pid"; else echo 'PID belongs to another process; refusing to stop it.';exit 1;fi
fi
rm -f "$DATA/service.pid"
echo 'Web service stopped; detached generation jobs continue.'
