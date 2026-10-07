"""Map selection, matched-support timelines and persistent human review records."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy.ndimage import label
from rasterio.features import shapes
from rasterio.warp import transform_geom, transform
from .scenes import validate_bbox, assert_aligned
from .indices import indices, water_screen

REVIEW_STATES = ["Needs review", "Likely change", "False positive", "Unclear"]


def timeline_key(scene, kind):
    return hashlib.sha256(json.dumps([scene.crs, list(scene.transform), scene.shape, kind]).encode()).hexdigest()[:20]


def drawn_bbox(feature):
    geom = feature.get("geometry", {})
    if geom.get("type") != "Polygon" or not geom.get("coordinates"):
        raise ValueError("Draw a rectangle or polygon around your region.")
    coords = np.asarray(geom["coordinates"][0], dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 4:
        raise ValueError("The region geometry is invalid.")
    return list(validate_bbox([coords[:, 0].min(), coords[:, 1].min(),
                               coords[:, 0].max(), coords[:, 1].max()]))


def analysis_key(before, after, mask):
    # Include actual rasters and selected mask so changed uploads/thresholds cannot inherit reviews.
    h = hashlib.sha256()
    for scene in (before, after):
        h.update(json.dumps([scene.metadata.get("id"), scene.metadata.get("datetime"),
                             scene.crs, list(scene.transform), scene.shape]).encode())
        h.update(np.ascontiguousarray(scene.data).tobytes())
    h.update(np.ascontiguousarray(mask, dtype=np.uint8).tobytes())
    return h.hexdigest()[:24]


def region_records(mask, scene, delta, scores=None):
    groups, count = label(mask)
    rows = []
    for rid in range(1, count + 1):
        region = groups == rid
        rr, cc = np.where(region)
        x, y = scene.transform @ (float(cc.mean()) + .5, float(rr.mean()) + .5)
        lon, lat = transform(scene.crs, "EPSG:4326", [x], [y])
        values = delta[region]
        row = {"region": rid, "area_ha": round(len(rr) * scene.pixel_area_m2 / 10000, 2),
               "longitude": lon[0], "latitude": lat[0],
               "mean_index_change": float(np.nanmean(values)) if np.isfinite(values).any() else None,
               "mean_model_score": (float(np.nanmean(scores[region])) if scores is not None else None)}
        rows.append(row)
    return pd.DataFrame(rows, columns=["region", "area_ha", "longitude", "latitude",
                                       "mean_index_change", "mean_model_score"]).sort_values("area_ha", ascending=False), groups


def load_reviews(path):
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get("reviews", {})


def save_review(path, reviews, rid, state, note):
    if state not in REVIEW_STATES:
        raise ValueError("Choose a valid review state.")
    if len(note) > 2000:
        raise ValueError("Keep notes under 2,000 characters.")
    reviews = {**reviews, str(int(rid)): {"status": state, "note": note,
               "updated_at": datetime.now(timezone.utc).isoformat()}}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"reviews": reviews}, indent=2))
    temp.replace(path)
    return reviews


def reviewed_geojson(groups, scene, rows, reviews):
    properties = {int(r["region"]): r for r in rows.to_dict("records")}
    features = []
    for geom, rid in shapes(groups.astype(np.int32), mask=groups > 0, transform=scene.transform):
        rid = int(rid)
        p = {**properties[rid], **reviews.get(str(rid), {"status": "Needs review", "note": ""})}
        p = {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in p.items()}
        features.append({"type": "Feature", "geometry": transform_geom(scene.crs, "EPSG:4326", geom),
                         "properties": p})
    return {"type": "FeatureCollection", "features": features}


def timeline_frame(scenes, kind, vegetation=.6, mndwi=0, forest_prior=None):
    scenes = sorted(scenes, key=lambda s: s.metadata.get("datetime", ""))
    if len(scenes) < 2:
        raise ValueError("Add at least two dated observations.")
    for scene in scenes[1:]:
        assert_aligned(scenes[0], scene)
    dates = [s.metadata["datetime"][:10] for s in scenes]
    if len(set(dates)) != len(dates):
        raise ValueError("Timeline observations must have different acquisition dates.")
    valid = np.logical_and.reduce([s.valid for s in scenes])
    ix = [indices(s) for s in scenes]
    if kind == "forest":
        support = valid & (ix[0]["NDVI"] >= vegetation)
        if forest_prior is not None:
            support &= forest_prior
        keys = ["NDVI", "NDMI", "NBR"]
    else:
        support = valid & np.logical_and.reduce([water_screen(s, mndwi)["water"] for s in scenes])
        keys = ["NDCI", "NDTI", "visible_turbidity_ratio"]
    if support.sum() < 10:
        raise ValueError("Not enough pixels observed on the same support at every date.")
    rows = []
    for s, idx in zip(scenes, ix):
        rows.append({"date": s.metadata["datetime"][:10], "scene": s.metadata["id"],
                     "clear_coverage_pct": round(100 * s.valid.mean(), 2),
                     "matched_support_ha": round(support.sum() * s.pixel_area_m2 / 10000, 2),
                     **{k: float(np.nanmedian(idx[k][support])) for k in keys}})
    return pd.DataFrame(rows), keys
