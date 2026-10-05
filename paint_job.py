"""Hunyuan3D Paint 2.0 with front, side and back reference images."""
from config import DATA_DIR, HUNYUAN_HOME, HUNYUAN_PYTHON, MODEL_DIR
import gc
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")

import numpy as np
import torch
import trimesh
from PIL import Image
from hy3dgen.texgen import Hunyuan3DPaintPipeline, Hunyuan3DTexGenConfig
from hy3dgen.texgen.utils.uv_warp_utils import mesh_uv_wrap

from preview import render_preview

MODEL_ROOT = MODEL_DIR / "paint"


def status(percent: int, message: str) -> None:
    print(f"PIPELINE_STATUS {percent}% {message}", flush=True)


def generate_multiview(self, input_images, control_images, camera_info):
    """Use all three supplied reference views; the stock wrapper uses one."""
    self.seed_everything(0)
    input_images = [img.resize((self.view_size, self.view_size)) for img in input_images]
    controls = []
    for img in control_images:
        img = img.resize((self.view_size, self.view_size))
        if img.mode == "L":
            img = img.point(lambda x: 255 if x > 1 else 0, mode="1")
        controls.append(img)
    n = len(controls) // 2
    return self.pipeline(
        input_images,
        num_inference_steps=30,
        generator=torch.Generator(device=self.pipeline.device).manual_seed(0),
        width=self.view_size,
        height=self.view_size,
        num_in_batch=n,
        camera_info_gen=[camera_info],
        camera_info_ref=[[0, 3, 6]],
        normal_imgs=[[controls[i] for i in range(n)]],
        position_imgs=[[controls[i + n] for i in range(n)]],
    ).images


def main(job_dir: Path) -> None:
    started = time.time()
    mesh_path = job_dir / "shape.glb"
    for name in ("front", "side", "back"):
        if not (job_dir / f"{name}.png").is_file():
            raise FileNotFoundError(f"Missing {name}.png reference")
    if not mesh_path.is_file():
        raise FileNotFoundError("Missing shape.glb")

    status(0, "Завантаження Paint 2.0 у RAM")
    config = Hunyuan3DTexGenConfig(
        str(MODEL_ROOT / "hunyuan3d-delight-v2-0"),
        str(MODEL_ROOT / "hunyuan3d-paint-v2-0"),
        "hunyuan3d-paint-v2-0",
    )
    config.device = "cpu"
    config.render_size = 512
    config.texture_size = 1024
    pipeline = Hunyuan3DPaintPipeline(config)
    status(20, "Моделі завантажені; CPU offload на CUDA")
    pipeline.enable_model_cpu_offload(device="cuda")
    type(pipeline.models["multiview_model"]).__call__ = generate_multiview

    images = []
    for name in ("front", "side", "back"):
        image = pipeline.recenter_image(Image.open(job_dir / f"{name}.png"))
        image.save(job_dir / f"prepared_{name}.png")
        images.append(image)
    status(40, "Три ракурси підготовлено; створення UV")
    mesh = mesh_uv_wrap(trimesh.load(mesh_path, force="mesh"))
    pipeline.render.load_mesh(mesh)
    elevs = config.candidate_camera_elevs
    azims = config.candidate_camera_azims
    weights = config.candidate_view_weights
    status(50, "UV готові; рендер normal і position guides")
    normal_maps = pipeline.render_normal_multiview(elevs, azims, use_abs_coor=True)
    position_maps = pipeline.render_position_multiview(elevs, azims)
    camera_info = [
        (((azim // 30) + 9) % 12) // {-20: 1, 0: 1, 20: 1, -90: 3, 90: 3}[elev]
        + {-20: 0, 0: 12, 20: 24, -90: 36, 90: 40}[elev]
        for azim, elev in zip(azims, elevs)
    ]
    status(60, "Guides готові; генерація текстури з трьох фото")
    multiviews = pipeline.models["multiview_model"](images, normal_maps + position_maps, camera_info)
    status(80, "Ракурси згенеровано; запікання атласу")
    multiviews = [view.resize((config.render_size, config.render_size)) for view in multiviews]
    texture, mask = pipeline.bake_from_multiview(multiviews, elevs, azims, weights, method=config.merge_method)
    status(90, "Атлас готовий; заповнення прогалин UV")
    mask_np = (mask.squeeze(-1).cpu().numpy() * 255).astype(np.uint8)
    texture = pipeline.texture_inpaint(texture, mask_np)
    pipeline.render.set_texture(texture)
    output = job_dir / "textured.glb"
    pipeline.render.save_mesh().export(output)
    del pipeline
    gc.collect()
    torch.cuda.empty_cache()

    scene = trimesh.load(output, force="scene")
    if not scene.geometry:
        raise RuntimeError("Текстурований GLB не містить геометрії")
    for part in scene.geometry.values():
        uv = getattr(part.visual, "uv", None)
        material = getattr(part.visual, "material", None)
        image = getattr(material, "image", None) or getattr(material, "baseColorTexture", None)
        if uv is None or len(uv) != len(part.vertices) or image is None:
            raise RuntimeError("GLB не містить повних UV або вбудованої текстури")
    status(95, "GLB перевірено; рендер front / 3/4 / side / back")
    render_preview(output, job_dir / "preview.png", textured=True)
    metrics = {
        "model": "Hunyuan3D Paint v2.0",
        "references": ["front", "side", "back"],
        "render_size": config.render_size,
        "texture_size": config.texture_size,
        "elapsed_seconds": round(time.time() - started, 2),
        "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "vertices": sum(len(g.vertices) for g in scene.geometry.values()),
        "triangles": sum(len(g.faces) for g in scene.geometry.values()),
        "output": str(output),
    }
    (job_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    status(100, "Текстурований GLB і прев’ю готові")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
