"""Four-angle contact sheet for completed GLB jobs."""
from pathlib import Path

import cv2
import numpy as np
import trimesh


def _colors(mesh, textured):
    if not textured:
        return np.tile(np.array([[156, 166, 177]], dtype=np.float32), (len(mesh.faces), 1))
    uv = np.asarray(mesh.visual.uv)
    material = mesh.visual.material
    image = getattr(material, "image", None) or getattr(material, "baseColorTexture", None)
    pixels = np.asarray(image.convert("RGB"))
    h, w = pixels.shape[:2]
    centers = uv[mesh.faces].mean(axis=1)
    x = np.clip((centers[:, 0] * (w - 1)).astype(int), 0, w - 1)
    y = np.clip(((1.0 - centers[:, 1]) * (h - 1)).astype(int), 0, h - 1)
    return pixels[y, x][:, ::-1].astype(np.float32)


def _view(mesh, colors, angle, label, width=560, height=720):
    yaw = np.deg2rad(angle)
    rotation = np.array(
        [[np.cos(yaw), 0, np.sin(yaw)], [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]],
        dtype=np.float32,
    )
    centered = mesh.vertices - mesh.bounds.mean(axis=0)
    vertices = centered @ rotation.T
    triangles = vertices[mesh.faces]
    normals = mesh.face_normals @ rotation.T
    extents = np.ptp(centered, axis=0)
    scale = min(width * .78 / max(extents[0], extents[2], 1e-3), height * .84 / max(extents[1], 1e-3))
    points = np.empty((len(triangles), 3, 2), dtype=np.int32)
    points[..., 0] = (triangles[..., 0] * scale + width / 2).astype(np.int32)
    points[..., 1] = (-triangles[..., 1] * scale + height / 2 + 10).astype(np.int32)
    order = np.argsort(triangles[..., 2].mean(axis=1))
    light = np.array([-.35, .45, .82], dtype=np.float32)
    light /= np.linalg.norm(light)
    shade = np.clip(.36 + .64 * np.abs(normals @ light), 0, 1)
    canvas = np.full((height, width, 3), (27, 31, 35), dtype=np.uint8)
    for idx in order:
        color = tuple(int(v) for v in np.clip(colors[idx] * shade[idx], 0, 255))
        cv2.fillConvexPoly(canvas, points[idx], color, lineType=cv2.LINE_AA)
    cv2.putText(canvas, label, (22, 40), cv2.FONT_HERSHEY_SIMPLEX, .85, (245, 245, 245), 2, cv2.LINE_AA)
    return canvas


def render_preview(mesh_path: Path, output: Path, textured: bool) -> None:
    scene = trimesh.load(mesh_path, force="scene")
    mesh = trimesh.util.concatenate(tuple(scene.geometry.values()))
    colors = _colors(mesh, textured)
    views = [_view(mesh, colors, angle, label) for angle, label in [(0, "FRONT"), (45, "3/4"), (90, "SIDE"), (180, "BACK")]]
    contact = np.vstack((np.hstack(views[:2]), np.hstack(views[2:])))
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), contact):
        raise RuntimeError("Could not save preview PNG")
