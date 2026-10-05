#!/usr/bin/env bash
set -euo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -f "$BASE/.env" ]]; then set -a; source "$BASE/.env"; set +a; fi
HUNYUAN_HOME=${HUNYUAN_HOME:-${WORKSHOP_STATE:-$HOME/.local/share/local-3d-workshop}/Hunyuan3D-2}
PYTHON=${HUNYUAN_PYTHON:-$HUNYUAN_HOME/.venv/bin/python}
[[ -x "$PYTHON" ]] || { echo 'Install first: docs/INSTALL_AGENT.uk.md'; exit 1; }
export PYTHONPATH="$HUNYUAN_HOME${PYTHONPATH:+:$PYTHONPATH}"
DATA=${WORKSHOP_DATA:-$BASE/runtime}
mkdir -p "$DATA"
echo $$ > "$DATA/service.pid"
exec "$PYTHON" -m uvicorn service:app --app-dir "$BASE" --host 127.0.0.1 --port "${1:-${WORKSHOP_PORT:-7861}}"
