"""Hunyuan3D-2mini Turbo shape job. Runs in the existing WSL Hunyuan venv."""
from config import DATA_DIR, HUNYUAN_HOME, HUNYUAN_PYTHON, MODEL_DIR
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")

import torch
import trimesh
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

from preview import render_preview


def status(percent: int, message: str) -> None:
    print(f"PIPELINE_STATUS {percent}% {message}", flush=True)


def main(job_dir: Path) -> None:
    started = time.time()
    source = job_dir / "front.png"
    output = job_dir / "shape.glb"
    mode = json.loads((job_dir / "job.json").read_text()).get("mode", "single")
    multiview = mode == "multiview"
    model_name = "Hunyuan3D-2mv" if multiview else "Hunyuan3D-2mini Turbo"
    model_dir = MODEL_DIR / ("multiview" if multiview else "mini-turbo")
    if not (model_dir / "model.fp16.safetensors").is_file():
        raise FileNotFoundError("Local Hunyuan3D-2mini Turbo weights are missing")

    status(0, "Перевірка референсу й локальних ваг")
    image = {view: Image.open(job_dir / f"{view}.png").convert("RGBA") for view in ("front", "left", "back")} if multiview else Image.open(source).convert("RGBA")
    # Opaque uploads need the existing Hunyuan foreground-removal step.
    from hy3dgen.rembg import BackgroundRemover
    remover = None
    def foreground(img):
        nonlocal remover
        if img.getchannel("A").getextrema()[0] == 255:
            if remover is None: remover = BackgroundRemover()
            return remover(img)
        return img
    image = {key: foreground(img) for key, img in image.items()} if multiview else foreground(image)
    del remover
    torch.cuda.reset_peak_memory_stats()
    status(10, f"Завантаження {model_name} у RAM, FP16")
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_single_file(
        str(model_dir / "model.fp16.safetensors"),
        str(model_dir / "config.yaml"),
        use_safetensors=True,
        device="cpu",
        dtype=torch.float16,
    )
    # This installed Hunyuan pipeline implements offload but does not expose
    # DiffusionPipeline.components, which its offload method expects.
    pipeline.components = {
        "conditioner": pipeline.conditioner,
        "model": pipeline.model,
        "vae": pipeline.vae,
    }
    pipeline.enable_model_cpu_offload(device="cuda")
    # In this repository __call__ allocates latents from self.device instead
    # of _execution_device; hooks keep the modules offloaded independently.
    pipeline.device = torch.device("cuda")
    status(30, "Модель завантажена; генерація сітки на GPU")
    mesh = pipeline(
        image=image,
        num_inference_steps=30 if multiview else 5,
        octree_resolution=256,
        num_chunks=4000,
        generator=torch.Generator(device="cuda").manual_seed(12345),
        output_type="trimesh",
    )[0]
    status(85, "Експорт сирої геометрії")
    mesh.export(output)
    del mesh, pipeline
    torch.cuda.empty_cache()

    scene = trimesh.load(output, force="scene")
    if not scene.geometry or sum(len(g.faces) for g in scene.geometry.values()) == 0:
        raise RuntimeError("GLB не містить придатної геометрії")
    status(92, "Перевірка GLB і створення front / 3/4 / side / back")
    render_preview(output, job_dir / "preview.png", textured=False)
    metrics = {
        "model": model_name,
        "mode": mode,
        "references": ["front", "left", "back"] if multiview else ["front"],
        "seed": 12345,
        "steps": 30 if multiview else 5,
        "octree_resolution": 256,
        "num_chunks": 4000,
        "elapsed_seconds": round(time.time() - started, 2),
        "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "vertices": sum(len(g.vertices) for g in scene.geometry.values()),
        "triangles": sum(len(g.faces) for g in scene.geometry.values()),
        "output": str(output),
    }
    (job_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    status(100, "Сирий mesh і прев’ю готові")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
