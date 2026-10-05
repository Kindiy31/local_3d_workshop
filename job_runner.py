"""Detached wrapper that leaves an exit code even if the dashboard restarts."""
from config import DATA_DIR, HUNYUAN_HOME, HUNYUAN_PYTHON, MODEL_DIR
import subprocess
import sys
import traceback
from pathlib import Path


def main():
    kind, folder = sys.argv[1], Path(sys.argv[2])
    if kind not in {"shape", "paint"}:
        raise ValueError("Unknown job kind")
    script = Path(__file__).parent / f"{kind}_job.py"
    code = 1
    try:
        with (folder / "console.log").open("a", encoding="utf-8", buffering=1) as log:
            command = [sys.executable, "-u", str(script), str(folder)]
            code = subprocess.call(command, stdout=log, stderr=subprocess.STDOUT, cwd=str(HUNYUAN_HOME))
    except BaseException:
        (folder / "runner_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        (folder / "exit_code.txt").write_text(str(code), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
