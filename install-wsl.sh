#!/usr/bin/env bash
# Run inside Ubuntu 22.04 after reviewing docs/INSTALL_AGENT.uk.md.
set -euo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -f "$BASE/.env" ]]; then set -a; source "$BASE/.env"; set +a; fi
export HUNYUAN_HOME=${HUNYUAN_HOME:-${WORKSHOP_STATE:-$HOME/.local/share/local-3d-workshop}/Hunyuan3D-2}
export HUNYUAN_PYTHON=${HUNYUAN_PYTHON:-$HUNYUAN_HOME/.venv/bin/python}
REV=f8db63096c8282cb27354314d896feba5ba6ff8a
command -v git >/dev/null; command -v nvcc >/dev/null; nvidia-smi >/dev/null
if [[ ! -d "$HUNYUAN_HOME/.git" ]]; then
 mkdir -p "$(dirname -- "$HUNYUAN_HOME")"
 git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git "$HUNYUAN_HOME"
 git -C "$HUNYUAN_HOME" checkout "$REV"
elif [[ $(git -C "$HUNYUAN_HOME" rev-parse HEAD) != "$REV" ]]; then
 echo 'Existing upstream revision differs. Inspect it; installer will not reset it.';exit 1
fi
[[ -x "$HUNYUAN_PYTHON" ]] || python3.10 -m venv "$HUNYUAN_HOME/.venv"
"$HUNYUAN_PYTHON" -m pip install 'pip<26' wheel setuptools
"$HUNYUAN_PYTHON" -m pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121
"$HUNYUAN_PYTHON" -m pip install -c "$BASE/constraints-ml.txt" -r "$HUNYUAN_HOME/requirements.txt" -r "$BASE/requirements-workshop.txt"
# Build for the actual GPU; e.g. TORCH_CUDA_ARCH_LIST=6.1 for GTX 1060.
export TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST:-$("$HUNYUAN_PYTHON" -c 'import torch; print("%d.%d" % torch.cuda.get_device_capability())')}
export MAX_JOBS=${MAX_JOBS:-2}
"$HUNYUAN_PYTHON" -m pip install --no-build-isolation "$HUNYUAN_HOME/hy3dgen/texgen/custom_rasterizer"
"$HUNYUAN_PYTHON" -m pip install --no-build-isolation "$HUNYUAN_HOME/hy3dgen/texgen/differentiable_renderer"
PYTHONPATH="$HUNYUAN_HOME" "$HUNYUAN_PYTHON" "$BASE/apply_offload_patch.py"
echo 'Runtime installed. Next: run download_models.py and doctor.py with this Python.'
