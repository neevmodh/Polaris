"""Visible-image screening. Never infer NIR indices or hectares from RGB uploads."""
from io import BytesIO
import zipfile
import json
import numpy as np
from PIL import Image, ImageOps
from scipy.ndimage import label
from .exports import png_bytes


def read_rgb(content):
    with Image.open(BytesIO(content)) as image:
        if image.width * image.height > 4_000_000:
            raise ValueError("Use images smaller than four million pixels.")
        image = ImageOps.exif_transpose(image)
        valid = np.asarray(image.convert("RGBA"))[..., 3] > 0
        return np.asarray(image.convert("RGB")), valid


def compare_rgb(before, after, valid, threshold=.12, min_pixels=8):
    if before.shape != after.shape or before.ndim != 3 or before.shape[-1] != 3:
        raise ValueError("Both RGB images must have identical dimensions and cover the same aligned view.")
    if valid.shape != before.shape[:2] or valid.sum() == 0:
        raise ValueError("The images do not have any comparable visible pixels.")
    a, b = before.astype(np.float32) / 255, after.astype(np.float32) / 255
    # Chromatic proportions reduce overall brightness differences; no automatic registration.
    ca = a / np.maximum(a.sum(axis=-1, keepdims=True), .05)
    cb = b / np.maximum(b.sum(axis=-1, keepdims=True), .05)
    change = np.max(np.abs(cb - ca), axis=-1)
    candidate = valid & (change > threshold)
    groups, _ = label(candidate)
    keep = np.bincount(groups.ravel()) >= min_pixels
    keep[0] = False
    mask = keep[groups]
    green_before = valid & (ca[..., 1] > ca[..., 0] + .04) & (ca[..., 1] > ca[..., 2] + .04)
    green_after = valid & (cb[..., 1] > cb[..., 0] + .04) & (cb[..., 1] > cb[..., 2] + .04)
    overlay = after.copy()
    overlay[mask] = (.35 * overlay[mask] + .65 * np.array([255, 96, 77])).astype(np.uint8)
    n = int(valid.sum())
    summary = {"analysis": "RGB visible-change screening", "comparable_pixels": n,
               "changed_pixels": int(mask.sum()), "changed_pct": round(100 * mask.sum() / n, 2),
               "green_before_pct": round(100 * green_before.sum() / n, 2),
               "green_after_pct": round(100 * green_after.sum() / n, 2),
               "threshold": threshold, "minimum_patch_pixels": min_pixels,
               "interpretation": "Color-change screening only. Input images must already be aligned. "
               "Clouds, viewpoint, season and exposure can cause alerts. No geospatial area, NDVI, "
               "trained forest-loss prediction or pollution measurement is available from RGB alone."}
    return {"mask": mask, "change": np.where(valid, change, np.nan), "overlay": overlay, "summary": summary}


def rgb_package(before, after, result):
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("summary.json", json.dumps(result["summary"], indent=2))
        z.writestr("before.png", png_bytes(before))
        z.writestr("after.png", png_bytes(after))
        z.writestr("visible_change.png", png_bytes(result["overlay"]))
        z.writestr("change_mask.png", png_bytes(result["mask"].astype(np.uint8) * 255))
    return out.getvalue()
