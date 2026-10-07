"""Public STAC ingestion; no credentials, fake fallback, or paid data required."""
from datetime import date
from pathlib import Path
import json
import math
import requests
import numpy as np
from .scenes import BANDS, Scene, read_remote_grid, utm_grid, validate_bbox

ENDPOINT = "https://earth-search.aws.element84.com/v1/search"

PRESETS = {
    "forest": {"name": "Rondônia forest frontier", "location": "Brazil · Amazon basin",
               "bbox": [-64.60, -9.70, -64.52, -9.62],
               "before": ["2019-07-01", "2019-09-30"], "after": ["2024-07-01", "2024-09-30"]},
    "lake": {"name": "Loktak Lake", "location": "Manipur · India",
             "bbox": [93.77, 24.47, 93.83, 24.53],
             "before": ["2020-01-01", "2020-03-31"], "after": ["2024-01-01", "2024-03-31"]},
}


def search(bbox, start, end, cloud=15):
    validate_bbox(bbox)
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("The date-range start must be before its end.")
    payload = {"collections": ["sentinel-2-c1-l2a"], "bbox": list(bbox),
               "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100,
               "query": {"eo:cloud_cover": {"lt": cloud}}}
    res = requests.post(ENDPOINT, json=payload, timeout=60)
    res.raise_for_status()
    items = res.json().get("features", [])
    # Require full ROI coverage: tile edges otherwise silently create unobserved pixels.
    w, s, e, n = bbox
    items = [f for f in items if f["bbox"][0] <= w and f["bbox"][1] <= s
             and f["bbox"][2] >= e and f["bbox"][3] >= n]
    if not items:
        raise ValueError("No covering clear scenes found. Widen the dates or choose a smaller region.")
    return sorted(items, key=lambda f: (f["properties"].get("eo:cloud_cover", 100), f["id"]))


def reflectance_parameters(item, asset):
    rb = asset.get("raster:bands", [{}])[0]
    scale = float(rb.get("scale", 0.0001))
    offset = float(rb.get("offset", 0))
    props = item["properties"]
    # COG providers sometimes bake in the ESA BOA offset. Do not subtract it twice.
    if props.get("earthsearch:boa_offset_applied") is True:
        offset = 0.0
    # Original, pre-baseline-04 products do not have a BOA radiometric offset.
    baseline = props.get("s2:processing_baseline")
    if baseline is not None and float(baseline) < 4:
        offset = 0.0
    return scale, offset


def fetch_scene(item, grid, log=None):
    arrays, sources = [], {}
    for band in BANDS:
        if log:
            log(f"Reading {item['id']} · {band}")
        asset = item["assets"][band]
        url = asset["href"]
        if not url.startswith("https://"):
            raise ValueError("The selected scene is not available over public HTTPS.")
        arr = read_remote_grid(url, grid, categorical=(band == "scl"))
        if band != "scl":
            scale, offset = reflectance_parameters(item, asset)
            arr = arr * scale + offset
            sources[band] = {"url": url, "scale": scale, "offset": offset}
        else:
            sources[band] = {"url": url}
        arrays.append(arr)
    props = item["properties"]
    crs, transform, _, _ = grid
    return Scene(np.stack(arrays), transform, crs, {
        "id": item["id"], "datetime": props["datetime"], "source": "Copernicus Sentinel-2 L2A / Earth Search",
        "cloud_cover_scene_pct": props.get("eo:cloud_cover"), "assets": sources,
        "stac_item": item, "processing_baseline": props.get("s2:processing_baseline"),
        "boa_offset_applied": props.get("earthsearch:boa_offset_applied"),
        "quality": "SCL classes 4, 5, 6 only; clouds, shadows, snow and uncertain pixels excluded",
    })


def fetch_pair(bbox, before_range, after_range, outdir, resolution=30, log=None):
    if before_range[1] >= after_range[0]:
        raise ValueError("Baseline and comparison ranges must not overlap.")
    grid = utm_grid(bbox, resolution)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    scenes = []
    for label, period in [("before", before_range), ("after", after_range)]:
        candidates = search(bbox, *period)
        scene = None
        for item in candidates[:3]:
            candidate = fetch_scene(item, grid, log)
            if candidate.valid.mean() >= 0.70:
                scene = candidate
                break
        if scene is None:
            raise ValueError("The best scenes have insufficient clear pixels in this region.")
        scene.metadata["bbox_wgs84"] = list(bbox)
        scene.metadata["selection_range"] = list(period)
        scene.save(outdir / f"{label}.npz")
        scenes.append(scene)
    return scenes


def hansen_reference(bbox, grid, outdir, log=None):
    w, s, e, n = bbox
    top = int(math.ceil(n / 10) * 10)
    left = int(math.floor(w / 10) * 10)
    if s < top - 10 or e > left + 10:
        raise ValueError("Reference export currently supports a region within one Hansen tile.")
    tile = f"{abs(top):02d}{'N' if top >= 0 else 'S'}_{abs(left):03d}{'E' if left >= 0 else 'W'}"
    base = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12"
    layers, sources = {}, {}
    for name in ["treecover2000", "lossyear", "datamask"]:
        url = f"{base}/Hansen_GFC-2024-v1.12_{name}_{tile}.tif"
        if log:
            log(f"Reading Hansen reference · {name}")
        # Zero means 'no loss' / 'no tree cover', not missing, in these layers.
        layers[name] = read_remote_grid(url, grid, categorical=True, nodata=None)
        sources[name] = url
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(outdir / "reference.npz", **layers)
    (outdir / "reference.json").write_text(json.dumps({
        "dataset": "Hansen Global Forest Change 2024 v1.12", "source": sources,
        "license": "CC BY 4.0", "reference_resolution_m": 30,
        "meaning": "Annual tree-cover loss, not a legal determination of deforestation.",
    }, indent=2))
    return layers
