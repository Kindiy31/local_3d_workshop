"""Local Ukrainian Hunyuan dashboard/API used by n8n workflows."""
from config import DATA_DIR, HUNYUAN_HOME, HUNYUAN_PYTHON, MODEL_DIR
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

import trimesh
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image, UnidentifiedImageError

BASE = Path(__file__).resolve().parent
JOBS = DATA_DIR / "jobs"
PYTHON = str(HUNYUAN_PYTHON)
N8N_WEBHOOK = os.environ.get("HUNYUAN_N8N_WEBHOOK", "")
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_MESH_BYTES = 100 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 50_000_000
STATUS_RE = re.compile(r"^PIPELINE_STATUS\s+(\d+)%\s+(.+)$", re.MULTILINE)
LOCK = threading.Lock()

app = FastAPI(title="Локальний Hunyuan 2D → 3D", docs_url="/api/docs")
JOBS.mkdir(parents=True, exist_ok=True)


def _folder(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(400, "Некоректний ID завдання")
    folder = JOBS / job_id
    if not folder.is_dir():
        raise HTTPException(404, "Завдання не знайдено")
    return folder


def _meta(folder: Path) -> dict:
    return json.loads((folder / "job.json").read_text(encoding="utf-8"))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat")
        return not stat.exists() or stat.read_text().rsplit(")", 1)[1].strip().split()[0] != "Z"
    except OSError:
        return False


def _status(folder: Path, gpu: bool = False) -> dict:
    meta = _meta(folder)
    log_path = folder / "console.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    markers = STATUS_RE.findall(log)
    percent, stage = (int(markers[-1][0]), markers[-1][1]) if markers else (0, "Очікування запуску")
    exit_path = folder / "exit_code.txt"
    if exit_path.exists():
        exit_code = int(exit_path.read_text().strip())
        state = "completed" if exit_code == 0 else "failed"
    else:
        exit_code = None
        pid = int((folder / "pid.txt").read_text()) if (folder / "pid.txt").exists() else 0
        state = "queued" if meta.get("queued") else "running" if pid and _alive(pid) else "starting" if time.time() - meta["created_at"] < 30 else "interrupted"
    if state == "queued":
        stage = "Очікує mesh " + meta["depends_on"][:8] if meta.get("depends_on") else "У черзі на GPU"
    ended = (exit_path.stat().st_mtime if exit_path.exists() else time.time())
    elapsed = max(0, int(ended - meta.get("started_at", meta["created_at"]))) if state != "queued" else 0
    mode = meta.get("mode", "single")
    expected = 47 * 60 if meta["kind"] == "shape" else 268 * 60
    eta = max(0, expected - elapsed) if state == "running" and mode != "multiview" else None
    if state == "completed":
        percent = 100
    files = [name for name in ("shape.glb", "textured.glb", "preview.png", "metrics.json", "console.log") if (folder / name).is_file()]
    data = {
        "id": meta["id"], "kind": meta["kind"], "state": state, "mode": mode,
        "percent": percent, "stage": stage, "elapsed_seconds": elapsed,
        "eta_seconds": eta, "eta_note": "Для режиму 3 ракурси ще немає виміряного часу; відсотки етапні" if mode == "multiview" else "Оцінка за попередніми запусками; відсотки умовні за етапами" if eta is not None else None,
        "exit_code": exit_code, "files": files,
        "n8n_notified": meta.get("n8n_notified", False),
        "created_at": meta["created_at"],
        "depends_on": meta.get("depends_on"), "paint_job_id": meta.get("paint_job_id"),
        "log_tail": "\n".join(log.splitlines()[-8:]) if state in {"failed", "interrupted"} else None,
    }
    if gpu and state == "running":
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            util, memory, temp = [int(part.strip()) for part in result.stdout.splitlines()[0].split(",")]
            data["gpu"] = {"utilization_percent": util, "memory_mib": memory, "temperature_c": temp}
        except Exception:
            data["gpu"] = None
    return data


def _active_job() -> Optional[str]:
    for folder in JOBS.iterdir():
        if folder.is_dir() and (folder / "job.json").exists():
            if _status(folder)["state"] in {"running", "starting"}:
                return folder.name
    return None


async def _save_image(upload: UploadFile, output: Path) -> None:
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Фото порожнє або перевищує 30 МБ")
    try:
        from io import BytesIO
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.convert("RGBA").save(output, format="PNG")
    except (UnidentifiedImageError, ValueError, OSError) as exc:
        raise HTTPException(400, f"Непридатне зображення: {exc}") from exc


async def _save_mesh(upload: UploadFile, output: Path) -> None:
    data = await upload.read(MAX_MESH_BYTES + 1)
    if not data or len(data) > MAX_MESH_BYTES:
        raise HTTPException(413, "GLB порожній або перевищує 100 МБ")
    output.write_bytes(data)
    try:
        scene = trimesh.load(output, force="scene")
        if not scene.geometry or sum(len(g.faces) for g in scene.geometry.values()) == 0:
            raise ValueError("немає геометрії")
    except Exception as exc:
        output.unlink(missing_ok=True)
        raise HTTPException(400, f"Непридатний GLB: {exc}") from exc


def _notify_n8n(job_id: str, kind: str, folder: Path) -> bool:
    if not N8N_WEBHOOK:
        return False
    payload = json.dumps({"job_id": job_id, "kind": kind}).encode("utf-8")
    try:
        request = urllib.request.Request(N8N_WEBHOOK, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=4) as response:
            success = 200 <= response.status < 300
    except Exception:
        success = False
    meta = _meta(folder)
    meta["n8n_notified"] = success
    (folder / "job.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return success


def _launch(folder: Path, kind: str, mode: str = "single", depends_on=None) -> dict:
    with LOCK:
        job_id = folder.name
        meta = {"id": job_id, "kind": kind, "mode": mode, "created_at": time.time(), "n8n_notified": False, "queued": True, "depends_on": depends_on}
        (folder / "job.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return _status(folder)


def _dispatch():
    while True:
      try:
       with LOCK:
        if _active_job():
            continue
        pending = sorted((p for p in JOBS.iterdir() if (p / "job.json").exists() and _meta(p).get("queued")), key=lambda p: _meta(p)["created_at"])
        if not pending:
            continue
        folder = pending[0]; meta = _meta(folder); kind = meta["kind"]
        if kind == "shape" and meta.get("mode") == "multiview" and not (MODEL_DIR / "multiview" / "ready.txt").is_file():
            continue
        dependency = meta.get("depends_on")
        if dependency:
            source = _folder(dependency); state = _status(source)["state"]
            if state in {"failed", "interrupted"}:
                meta["queued"] = False
                (folder / "console.log").write_text("Mesh не завершився успішно; Paint не запущено.", encoding="utf-8")
                (folder / "exit_code.txt").write_text("1")
                (folder / "job.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                continue
            if state != "completed":
                continue
            shutil.copy2(source / "shape.glb", folder / "shape.glb")
        meta["queued"] = False; meta["started_at"] = time.time()
        (folder / "job.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        log = (folder / "runner.log").open("a", encoding="utf-8")
        process = subprocess.Popen(
            [PYTHON, "-u", str(BASE / "job_runner.py"), kind, str(folder)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            cwd=str(HUNYUAN_HOME), start_new_session=True,
        )
        log.close()
        (folder / "pid.txt").write_text(str(process.pid), encoding="utf-8")
       _notify_n8n(folder.name, kind, folder)
      except Exception:
        import traceback
        traceback.print_exc()
      finally:
        time.sleep(5)


@app.on_event("startup")
def start_queue():
    threading.Thread(target=_dispatch, daemon=True, name="gpu-queue").start()


@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    model = MODEL_DIR / "multiview"
    return {"ok": True, "n8n_webhook": N8N_WEBHOOK, "gpu_busy_job": _active_job(), "multiview_ready": all((model / name).is_file() for name in ("config.yaml", "model.fp16.safetensors", "ready.txt"))}


@app.get("/api/jobs")
def jobs():
    folders = [p for p in JOBS.iterdir() if p.is_dir() and (p / "job.json").exists()]
    return sorted((_status(p) for p in folders), key=lambda job: job["created_at"], reverse=True)


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    return _status(_folder(job_id), gpu=True)


@app.post("/api/jobs/{job_id}/notify-n8n")
def notify(job_id: str):
    folder = _folder(job_id)
    return {"notified": _notify_n8n(job_id, _meta(folder)["kind"], folder)}


@app.post("/api/shape")
async def shape(front: UploadFile = File(...), mode: str = Form("single"), left: Optional[UploadFile] = File(None), back: Optional[UploadFile] = File(None), auto_paint: bool = Form(False)):
    if mode not in {"single", "multiview"}:
        raise HTTPException(400, "Невідомий режим генерації")
    if auto_paint and (mode != "multiview" or not left or not back):
        raise HTTPException(400, "Автоматичний Paint потребує трьох ракурсів")
    if mode == "multiview":
        if not left or not back:
            raise HTTPException(400, "Для 3 ракурсів потрібні фото спереду, зліва й ззаду")
        model = MODEL_DIR / "multiview"
        # Accept persistent queued work while the model download finishes.
    folder = JOBS / uuid.uuid4().hex
    folder.mkdir()
    try:
        await _save_image(front, folder / "front.png")
        if mode == "multiview":
            await _save_image(left, folder / "left.png")
            await _save_image(back, folder / "back.png")
        if auto_paint:
            paint_folder = JOBS / uuid.uuid4().hex
            paint_folder.mkdir()
            for source, target in (("front", "front"), ("left", "side"), ("back", "back")):
                shutil.copy2(folder / f"{source}.png", paint_folder / f"{target}.png")
            # Reserve both stages atomically before the dispatcher can start.
            with LOCK:
                created = time.time()
                for f, k, m, dep in ((folder,"shape",mode,None),(paint_folder,"paint","single",folder.name)):
                    meta = {"id":f.name,"kind":k,"mode":m,"created_at":created if k=="shape" else created+.001,"queued":True,"depends_on":dep,"n8n_notified":False}
                    if k=="shape": meta["paint_job_id"] = paint_folder.name
                    (f / "job.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
            return _status(folder)
        return _launch(folder, "shape", mode)
    except Exception:
        if not (folder / "job.json").exists():
            shutil.rmtree(folder)
        raise


@app.post("/api/paint")
async def paint(
    front: UploadFile = File(...), side: UploadFile = File(...), back: UploadFile = File(...),
    shape_job_id: Optional[str] = Form(None), mesh: Optional[UploadFile] = File(None),
):
    if not shape_job_id and not mesh:
        raise HTTPException(400, "Вкажіть готове shape-завдання або завантажте сирий GLB")
    folder = JOBS / uuid.uuid4().hex
    folder.mkdir()
    try:
        if shape_job_id:
            source_folder = _folder(shape_job_id)
            if _status(source_folder)["state"] != "completed" or not (source_folder / "shape.glb").exists():
                raise HTTPException(409, "Сирий mesh ще не готовий")
            shutil.copy2(source_folder / "shape.glb", folder / "shape.glb")
        else:
            await _save_mesh(mesh, folder / "shape.glb")
        for name, upload in (("front", front), ("side", side), ("back", back)):
            await _save_image(upload, folder / f"{name}.png")
        return _launch(folder, "paint")
    except Exception:
        if not (folder / "job.json").exists():
            shutil.rmtree(folder)
        raise


@app.get("/api/jobs/{job_id}/files/{name}")
def file(job_id: str, name: str):
    if name not in {"shape.glb", "textured.glb", "preview.png", "metrics.json", "console.log"}:
        raise HTTPException(404, "Файл не знайдено")
    path = _folder(job_id) / name
    if not path.is_file():
        raise HTTPException(404, "Файл ще не готовий")
    return FileResponse(path, filename=name)
