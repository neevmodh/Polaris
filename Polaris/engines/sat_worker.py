"""Polaris satellite engine: a JSON-lines worker over the Task3 `monitor` package.

It only reads Task3's core modules (scenes, analysis, learning, indices, exports, water_model, catalog, workspace);
it never writes into Task3. Everything it creates (custom scenes, uploads, reviews, U-Net cache) lives in Polaris/data.
Requests are handled on a small thread pool so a slow fetch or U-Net run does not block other calls."""
import re, base64, contextvars, hashlib, json, math, os, sys, threading, time, traceback, uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

TASK3 = Path(os.environ.get("TASK3_DIR", Path(__file__).resolve().parents[2] / "Task3")).resolve()
DATA = Path(os.environ.get("POLARIS_DATA", Path(__file__).resolve().parents[1] / "data")).resolve()
os.chdir(TASK3); sys.path.insert(0, str(TASK3))
_proto, _lock = sys.stdout, threading.Lock()
sys.stdout = sys.stderr

import numpy as np, pandas as pd
from PIL import Image
from monitor.analysis import forest_analysis, lake_analysis
from monitor.catalog import PRESETS, fetch_pair, fetch_scene, search
from monitor.exports import bundle, json_text, overlay, rgb
from monitor.learning import baseline_forest_prior
from monitor.scenes import Scene, assert_aligned, from_geotiff, validate_bbox
from monitor import water_model
from monitor.workspace import REVIEW_STATES, analysis_key, load_reviews, region_records, reviewed_geojson, save_review, timeline_frame
from monitor.image_inputs import compare_rgb, read_rgb, rgb_package

for d in ("reviews", "custom", "uploads", "unet", "timeline"): (DATA / d).mkdir(parents=True, exist_ok=True)
MODEL = TASK3 / "models" / "forest_rf.joblib"
CASES = {"forest": "forest", "lake": "lake"}
_scenes, _analyses, _jobs = {}, {}, {}
_slock, _alock = threading.Lock(), threading.Lock()
_review_lock = threading.Lock()                          # one read-modify-write on any review file at a time
_owner = contextvars.ContextVar("polaris_owner", default=None)
JOB_TTL_S = 3600
MAX_INFLIGHT = 12                                        # requests running or queued; beyond this the engine says it is busy
_slots = threading.BoundedSemaphore(MAX_INFLIGHT)


def owner_ns():
    """The visitor this request belongs to. Preset demo cases are public; every uploaded or fetched case is private to one owner."""
    o = _owner.get()
    return o if o and re.fullmatch(r"[0-9a-f]{16}", o) else None


def _owned_key(owner, *parts):
    h = hashlib.sha256(); h.update((owner or "anonymous").encode()); h.update(b"\0")
    for x in parts: h.update(x if isinstance(x, bytes) else str(x).encode()); h.update(b"\0")
    return h.hexdigest()[:16]
_unet_lock = threading.Lock()


# ----------------------------------------------------------------- helpers
def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, (np.floating, float)): return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.bool_): return bool(o)
    if isinstance(o, pd.DataFrame): return clean(o.to_dict(orient="records"))
    return o


def png_url(arr):
    out = BytesIO(); Image.fromarray(arr).save(out, format="PNG", optimize=False)
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def ramp(stops):
    pos = np.array([p for p, _ in stops], float); col = np.array([c for _, c in stops], float)
    def f(t):
        t = np.clip(np.nan_to_num(t, nan=0.0), 0, 1)
        return np.stack([np.interp(t, pos, col[:, i]) for i in range(3)], -1)
    f.stops = [("#%02x%02x%02x" % tuple(int(v) for v in c), float(p)) for p, c in stops]
    return f


DIVERGING = ramp([(0, (192, 57, 43)), (.25, (241, 164, 91)), (.5, (245, 240, 214)), (.75, (150, 205, 130)), (1, (26, 130, 80))])
HEAT = ramp([(0, (255, 247, 224)), (.4, (252, 188, 90)), (.75, (222, 90, 40)), (1, (140, 20, 40))])
GREEN = ramp([(0, (240, 248, 224)), (.5, (130, 200, 110)), (1, (10, 90, 60))])
BROWN = ramp([(0, (252, 246, 228)), (.5, (214, 172, 100)), (1, (110, 70, 30))])
MUTED = np.array([23, 33, 31], np.uint8)


def heat_image(values, scene, cmap, lo, hi):
    t = (values - lo) / (hi - lo)
    img = (cmap(t) ).astype(np.uint8)
    img[~(np.isfinite(values) & scene.valid)] = MUTED
    return img, {"stops": cmap.stops, "min": lo, "max": hi}


def to_wgs84_bounds(scene):
    from rasterio.warp import transform_bounds
    w, s, e, n = scene.bounds
    return [float(v) for v in transform_bounds(scene.crs, "EPSG:4326", w, s, e, n)]


def scene_info(s, label):
    m = s.metadata
    return {"label": label, "id": m.get("id"), "datetime": (m.get("datetime") or "")[:10], "source": m.get("source"),
            "cloud_cover_scene_pct": m.get("cloud_cover_scene_pct"), "processing_baseline": m.get("processing_baseline"),
            "quality": m.get("quality"), "crs": s.crs, "resolution_m": abs(s.transform.a), "shape": list(s.shape),
            "clear_pct": float(s.valid.mean() * 100), "bounds_wgs84": to_wgs84_bounds(s),
            "bands": ["B02", "B03", "B04", "B08", "B11", "B12", "B05", "SCL"]}


# ----------------------------------------------------------------- cases
def load_case(case):
    if case in ("forest", "lake"):
        folder = TASK3 / "data" / case
    elif re.fullmatch(r"(custom|upload):[0-9a-f]{16}", case):
        folder = DATA / ("custom" if case.startswith("custom") else "uploads") / case.split(":", 1)[1]
    else:
        raise ValueError(f"Unknown case {case!r}")
    if case not in ("forest", "lake"):
        # Ownership is checked on EVERY call, before the in-memory cache is consulted: a cached pair must not be
        # reachable by a session that does not own it.
        mine = owner_ns(); tag = folder / "owner.txt"
        if not mine or not tag.exists() or tag.read_text().strip() != mine:
            raise ValueError("This observation pair is not available to this session.")
    with _slock:
        if case in _scenes: return _scenes[case]
    if not (folder / "before.npz").exists() or not (folder / "after.npz").exists():
        raise ValueError("This observation pair is not cached. Prepare it first.")
    pair = (Scene.load(folder / "before.npz"), Scene.load(folder / "after.npz"))
    assert_aligned(*pair)
    with _slock: _scenes[case] = pair
    return pair


def case_card(case, kind, name, location, folder_meta=None):
    b, a = load_case(case)
    return {"id": case, "kind": kind, "name": name or b.metadata.get("region", case), "location": location,
            "before": scene_info(b, "Baseline"), "after": scene_info(a, "Comparison"),
            "size": [b.shape[1], b.shape[0]], "preset": folder_meta}


def list_custom():
    out, mine = [], owner_ns()
    if not mine: return out
    for p in sorted((DATA / "custom").glob("*/before.npz")):
        try:
            tag = p.parent / "owner.txt"
            if not tag.exists() or tag.read_text().strip() != mine: continue
            b = Scene.load(p); key = p.parent.name
            out.append({"id": f"custom:{key}", "name": b.metadata.get("region", key), "kind": b.metadata.get("kind", "forest"),
                        "bbox": b.metadata.get("bbox_wgs84"), "before": b.metadata["datetime"][:10]})
        except Exception: continue
    return out


def meta(_):
    cases = []
    for kind in ("forest", "lake"):
        p = PRESETS[kind]
        try: cases.append(case_card(kind, kind, p["name"], p["location"], p))
        except Exception as exc: cases.append({"id": kind, "kind": kind, "name": p["name"], "error": str(exc)})
    metrics_path = TASK3 / "models" / "metrics.json"
    return {"cases": cases, "custom": list_custom(), "forest_model": MODEL.exists(), "unet": water_model.available(),
            "metrics": json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None,
            "review_states": REVIEW_STATES, "presets": {k: {"bbox": v["bbox"], "before": v["before"], "after": v["after"], "name": v["name"]} for k, v in PRESETS.items()}}


# ----------------------------------------------------------------- analysis
def unet_masks(case, before, after):
    masks = []
    for s in (before, after):
        key = hashlib.sha256(json.dumps([s.metadata.get("id"), s.metadata.get("datetime"), s.shape, s.crs]).encode()).hexdigest()[:20]
        path = DATA / "unet" / f"{key}.npy"
        if path.exists(): masks.append(np.load(path)); continue
        with _unet_lock:
            if path.exists(): masks.append(np.load(path)); continue
            m = water_model.segment(s); np.save(path, m); masks.append(m)
    return tuple(masks)


def _params(a):
    return {"kind": a["kind"], "case": a["case"], "detector": a.get("detector", "Trained random forest"),
            "threshold": float(a.get("threshold", .5)), "drop": float(a.get("drop", .2)), "vegetation": float(a.get("vegetation", .6)),
            "patches": int(a.get("patches", 4)), "water": a.get("water", "Spectral open-water mask"),
            "mndwi": float(a.get("mndwi", 0)), "algae": float(a.get("algae", .1))}


def run_analysis(a):
    p = _params(a); key = json.dumps(p, sort_keys=True)
    with _alock:
        if key in _analyses: return _analyses[key]
    before, after = load_case(p["case"])
    if p["kind"] == "forest":
        if not (0 < p["patches"] <= 100): raise ValueError("Minimum patch must be between 1 and 100 pixels.")
        prior = None
        if p["case"] == "forest" and (TASK3 / "data/forest/reference.npz").exists():
            with np.load(TASK3 / "data/forest/reference.npz", allow_pickle=False) as z:
                prior = baseline_forest_prior(before, {k: z[k] for k in z.files})
        use_model = p["detector"] == "Trained random forest" and MODEL.exists()
        r = forest_analysis(before, after, p["drop"], p["vegetation"], p["patches"], MODEL if use_model else None, p["threshold"], prior)
        r["prior_used"] = prior is not None; mask = r["loss"]
        r["detector_used"] = "Trained random forest" if use_model else "NDVI screening baseline"
        r["detector_fallback"] = "The trained forest model file is missing, so the NDVI screening baseline was used instead." if p["detector"] == "Trained random forest" and not use_model else None
    else:
        want_unet = p["water"] == "Pretrained U-Net"
        wm = unet_masks(p["case"], before, after) if want_unet and water_model.available() else None
        r = lake_analysis(before, after, p["mndwi"], p["algae"], wm); mask = r["alerts"]
        r["water_method"] = "Pretrained U-Net" if wm is not None else "Spectral open-water mask"
        r["water_fallback"] = "The pretrained U-Net is not installed on this server, so the spectral open-water mask was used instead." if want_unet and wm is None else None
    delta = r["delta"]
    rows, groups = region_records(mask, after, delta, r.get("scores"))
    r.update(mask=mask, rows=rows, groups=groups, key=analysis_key(before, after, mask), params=p)
    with _alock:
        if len(_analyses) > 24: _analyses.pop(next(iter(_analyses)))
        _analyses[key] = r
    return r


def layer_image(r, layer, before, after):
    kind, legend = r["params"]["kind"], None
    if layer == "rgb": img = rgb(after)
    elif kind == "forest" and layer == "alerts": img = overlay(after, r["mask"])
    elif kind == "forest" and layer == "ndvi_change": img, legend = heat_image(r["delta"], after, DIVERGING, -.4, .4)
    elif kind == "forest" and layer == "ml_score":
        if r["scores"] is None: raise ValueError("Select the trained random forest to see model scores.")
        img, legend = heat_image(r["scores"], after, HEAT, 0, 1)
    elif kind == "lake" and layer == "algae_change": img, legend = heat_image(r["delta"], after, DIVERGING, -.2, .2)
    elif kind == "lake" and layer == "algae": img, legend = heat_image(r["after"]["NDCI"], after, GREEN, -.2, .4)
    elif kind == "lake" and layer == "turbidity": img, legend = heat_image(r["after"]["NDTI"], after, BROWN, -.3, .3)
    elif kind == "lake" and layer == "water": img = overlay(after, r["after"]["water"], (98, 211, 234))
    elif kind == "lake" and layer == "alerts": img = overlay(after, r["mask"])
    else: raise ValueError(f"Unknown layer {layer!r} for {kind}")
    return img, legend


def regions_payload(r, after, limit=60):
    rows = r["rows"]; h, w = after.shape
    reviews = load_reviews(review_path(r))
    out = []
    for rec in rows.head(limit).to_dict("records"):
        rid = int(rec["region"]); rr, cc = np.where(r["groups"] == rid)
        rv = reviews.get(str(rid), {})
        out.append({**rec, "region": rid, "x": float(cc.mean() + .5) / w, "y": float(rr.mean() + .5) / h,
                    "status": rv.get("status", "Needs review"), "note": rv.get("note", "")})
    return out, len(rows), sum(1 for v in reviews.values() if v.get("status") != "Needs review")


def analyze(a):
    t0 = time.time(); r = run_analysis(a); before, after = load_case(r["params"]["case"])
    img, legend = layer_image(r, a.get("layer", "alerts" if r["params"]["kind"] == "forest" else "algae_change"), before, after)
    regions, total, reviewed = regions_payload(r, after)
    s = dict(r["summary"])
    return {"summary": s, "layer": a.get("layer"), "image": png_url(img), "legend": legend, "size": [after.shape[1], after.shape[0]],
            "regions": regions, "region_total": total, "reviewed": reviewed, "key": r["key"], "table": r.get("table"),
            "model_metrics": r.get("metrics"), "scores_available": r.get("scores") is not None, "prior_used": r.get("prior_used"),
            "review_scope": "public demo" if r["params"]["case"] in ("forest", "lake") else "private",
            "method": r.get("water_method") or r.get("detector_used"), "fallback": r.get("water_fallback") or r.get("detector_fallback"),
            "seconds": round(time.time() - t0, 2)}


def scene_images(a):
    before, after = load_case(a["case"])
    return {"before": png_url(rgb(before)), "after": png_url(rgb(after)), "size": [after.shape[1], after.shape[0]],
            "before_info": scene_info(before, "Baseline"), "after_info": scene_info(after, "Comparison")}


def crop(a):
    r = run_analysis(a); before, after = load_case(r["params"]["case"]); rid = int(a["region"])
    rr, cc = np.where(r["groups"] == rid)
    if not len(rr): raise ValueError("Unknown region.")
    ys = slice(max(0, rr.min() - 8), min(after.shape[0], rr.max() + 9)); xs = slice(max(0, cc.min() - 8), min(after.shape[1], cc.max() + 9))
    return {"before": png_url(rgb(before)[ys, xs]), "after": png_url(overlay(after, r["groups"] == rid)[ys, xs])}


def review_path(r):
    """Demo cases share one public review store; any other case keeps its reviews under its owner."""
    ns = "public" if r["params"]["case"] in ("forest", "lake") else (owner_ns() or "none")
    return DATA / "reviews" / ns / f"{r['key']}.json"


def review(a):
    r = run_analysis(a); path = review_path(r)
    with _review_lock:                                   # load, change and save as one step, or a concurrent save is lost
        save_review(path, load_reviews(path), int(a["region"]), a["status"], str(a.get("note", ""))[:2000])
        done = sum(1 for v in load_reviews(path).values() if v.get("status") != "Needs review")
    return {"ok": True, "reviewed": done, "scope": "public demo" if r["params"]["case"] in ("forest", "lake") else "private"}


def export(a):
    r = run_analysis(a); before, after = load_case(r["params"]["case"]); kind = r["params"]["kind"]
    reviews = load_reviews(review_path(r))
    queue = r["rows"].assign(status=[reviews.get(str(int(i)), {}).get("status", "Needs review") for i in r["rows"].region],
                             note=[reviews.get(str(int(i)), {}).get("note", "") for i in r["rows"].region])
    geo = reviewed_geojson(r["groups"], after, r["rows"], reviews)
    what = a.get("what", "package")
    if what == "summary": return {"name": f"polaris_{kind}_summary.json", "mime": "application/json", "text": json_text(r["summary"])}
    if what == "geojson": return {"name": f"polaris_{kind}_reviewed_regions.geojson", "mime": "application/geo+json", "text": json_text(geo)}
    if what == "csv": return {"name": f"polaris_{kind}_review_queue.csv", "mime": "text/csv", "text": queue.to_csv(index=False)}
    if kind == "forest":
        arrays = {"ndvi_change": r["delta"], "loss_mask": np.where(r["valid"], r["mask"].astype(float), np.nan)}
        if r["scores"] is not None: arrays["ml_score"] = r["scores"]
        table = r["alerts"].to_csv(index=False)
    else:
        arrays = {"ndci_change": r["delta"], "ndci_after": r["after"]["NDCI"], "ndti_after": r["after"]["NDTI"], "water_mask": r["after"]["water"].astype(float)}
        table = r["table"].to_csv(index=False)
    z = bundle(r["summary"], before, after, arrays, r["mask"], r.get("metrics"), table, {"review_queue.csv": queue.to_csv(index=False), "reviewed_regions.geojson": json_text(geo)})
    return {"name": f"polaris_{kind}_analysis.zip", "mime": "application/zip", "b64": base64.b64encode(z).decode()}


# ----------------------------------------------------------------- custom fetch and upload
def fetch_start(a):
    bbox = [float(x) for x in a["bbox"]]; validate_bbox(bbox)
    before_range, after_range = [str(x) for x in a["before"]], [str(x) for x in a["after"]]
    kind = a.get("kind", "forest"); name = str(a.get("name") or "Custom region")[:60]
    mine = owner_ns()
    if not mine: raise ValueError("A session is required to fetch a region.")
    _expire_jobs()
    key = _owned_key(mine, json.dumps([bbox, before_range, after_range]))
    folder = DATA / "custom" / key; job = uuid.uuid4().hex[:10]
    _jobs[job] = {"state": "running", "log": [], "case": f"custom:{key}", "error": None, "owner": mine, "t": time.time()}

    def work():
        _owner.set(mine)
        try:
            if (folder / "before.npz").exists() and (folder / "after.npz").exists():
                _jobs[job]["log"].append("Using the cached pair for this exact request.")
            else:
                scenes = fetch_pair(bbox, before_range, after_range, folder, log=lambda s: _jobs[job]["log"].append(str(s)))
                for label, sc in zip(["before", "after"], scenes):
                    sc.metadata.update(region=name, kind=kind); sc.save(folder / f"{label}.npz")
                (folder / "owner.txt").write_text(mine)
            with _slock: _scenes.pop(f"custom:{key}", None)
            load_case(f"custom:{key}"); _jobs[job]["state"] = "done"
        except Exception as exc:
            _jobs[job].update(state="error", error=str(exc))
    threading.Thread(target=work, daemon=True).start()
    return {"job": job, "case": f"custom:{key}"}


def _expire_jobs():
    now = time.time()
    for k in [k for k, v in _jobs.items() if now - v.get("t", now) > JOB_TTL_S]: _jobs.pop(k, None)


def fetch_status(a):
    _expire_jobs()
    j = _jobs.get(a["job"])
    if not j or j.get("owner") != owner_ns(): raise ValueError("Unknown job.")
    return {k: v for k, v in {**j, "log": j["log"][-12:]}.items() if k not in ("owner", "t")}


def upload(a):
    scale = 1 if a.get("encoding", "float") == "float" else .0001
    raw = [base64.b64decode(a["before_b64"]), base64.b64decode(a["after_b64"])]
    b = from_geotiff(raw[0], scale, str(a["before_date"]), str(a.get("before_name", "baseline.tif")))
    af = from_geotiff(raw[1], scale, str(a["after_date"]), str(a.get("after_name", "comparison.tif")))
    assert_aligned(b, af)
    name = str(a.get("name") or "Uploaded pair")[:60]
    for s in (b, af): s.metadata.update(region=name)
    mine = owner_ns()
    if not mine: raise ValueError("A session is required to upload rasters.")
    # Identity is every byte of both files plus everything that changes how they are read, so two different
    # payloads can never share a case, and an identical one reuses its own analyses safely.
    key = _owned_key(mine, raw[0], raw[1], a.get("encoding", "float"), a["before_date"], a["after_date"], a.get("kind", "forest"), name)
    folder = DATA / "uploads" / key
    if not (folder / "before.npz").exists():
        b.save(folder / "before.npz"); af.save(folder / "after.npz"); (folder / "owner.txt").write_text(mine)
    return {"case": f"upload:{key}", "card": case_card(f"upload:{key}", a.get("kind", "forest"), name, "User-supplied rasters")}


# ----------------------------------------------------------------- timeline: extra dated observations on the same grid
def _tl_dir(case): return DATA / "timeline" / hashlib.sha256(case.encode()).hexdigest()[:20]


def _tl_scenes(case):
    before, after = load_case(case)
    extras = [Scene.load(f) for f in sorted(_tl_dir(case).glob("*.npz"))] if _tl_dir(case).exists() else []
    inside = [e for e in extras if before.metadata["datetime"][:10] < e.metadata["datetime"][:10] < after.metadata["datetime"][:10]]
    return before, after, inside


def timeline(a):
    case, kind = a["case"], a["kind"]
    before, after, extras = _tl_scenes(case)
    chosen = [e for e in extras if not a.get("only") or e.metadata["datetime"][:10] in a["only"]]
    prior = None
    if kind == "forest" and case == "forest" and (TASK3 / "data/forest/reference.npz").exists():
        with np.load(TASK3 / "data/forest/reference.npz", allow_pickle=False) as z:
            prior = baseline_forest_prior(before, {k: z[k] for k in z.files})
    table, keys = timeline_frame([before, *chosen, after], kind, float(a.get("vegetation", .6)), float(a.get("mndwi", 0)), prior)
    return {"table": table, "keys": keys, "observations": [{"date": e.metadata["datetime"][:10], "id": e.metadata["id"], "source": e.metadata.get("source", ""), "clear_pct": float(e.valid.mean() * 100)} for e in extras]}


def timeline_remove(a):
    d = _tl_dir(a["case"]); f = d / f"{a['date']}.npz"
    if f.exists(): f.unlink()
    return {"ok": True}


def _store_extra(case, scene):
    before, after = load_case(case); assert_aligned(before, scene)
    day = scene.metadata["datetime"][:10]
    if not (before.metadata["datetime"][:10] < day < after.metadata["datetime"][:10]):
        raise ValueError(f"The extra observation ({day}) must fall between the baseline and comparison dates.")
    d = _tl_dir(case); d.mkdir(parents=True, exist_ok=True); scene.save(d / f"{day}.npz")
    return {"date": day, "id": scene.metadata["id"]}


def timeline_upload(a):
    scale = 1 if a.get("encoding", "float") == "float" else .0001
    scene = from_geotiff(base64.b64decode(a["b64"]), scale, str(a["date"]), str(a.get("name", "timeline.tif")))
    return _store_extra(a["case"], scene)          # alignment and date-window checks happen there


def timeline_fetch_start(a):
    case = a["case"]; before, after = load_case(case)
    bbox = before.metadata.get("bbox_wgs84")
    if not bbox: raise ValueError("This pair has no recorded bounding box, so extra dates cannot be fetched. Upload a raster instead.")
    start, end = str(a["start"]), str(a["end"]); job = uuid.uuid4().hex[:10]
    _jobs[job] = {"state": "running", "log": ["Searching the public catalogue…"], "case": case, "error": None}

    def work():
        try:
            grid = (before.crs, before.transform, before.shape[1], before.shape[0])
            for item in search(bbox, start, end)[:3]:
                _jobs[job]["log"].append(f"Reading {item['id']}")
                sc = fetch_scene(item, grid, log=None)
                if sc.valid.mean() >= 0.70:
                    sc.metadata["bbox_wgs84"] = list(bbox); _store_extra(case, sc); _jobs[job]["state"] = "done"; return
            raise ValueError("The best scenes in this window have too few clear pixels.")
        except Exception as exc:
            _jobs[job].update(state="error", error=str(exc))
    threading.Thread(target=work, daemon=True).start()
    return {"job": job}


# ----------------------------------------------------------------- RGB image studio
def rgb_compare(a):
    if a.get("demo"):
        kind = a.get("kind", "forest"); raw = [(TASK3 / "outputs" / kind / n).read_bytes() for n in ("before.png", "after.png")]; names = ["Prepared baseline RGB", "Prepared comparison RGB"]
    else:
        raw = [base64.b64decode(a["before_b64"]), base64.b64decode(a["after_b64"])]; names = [a.get("before_name", "before"), a.get("after_name", "after")]
    try:
        (b, vb), (af, va) = [read_rgb(x) for x in raw]
    except Exception as exc:
        raise ValueError("One of the images could not be read as a PNG or JPEG.") from exc
    if b.shape != af.shape:
        raise ValueError(f"The images have different dimensions ({b.shape[1]}x{b.shape[0]} and {af.shape[1]}x{af.shape[0]}). Align and crop them to the same view first.")
    thr, patch = float(a.get("threshold", .12)), int(a.get("patch", 8))
    res = compare_rgb(b, af, vb & va, thr, patch)
    return {"before": png_url(b), "after": png_url(af), "overlay": png_url(res["overlay"]), "summary": res["summary"], "size": [b.shape[1], b.shape[0]], "names": names,
            "package_b64": base64.b64encode(rgb_package(b, af, res)).decode() if a.get("package") else None}


CMDS = {"timeline": timeline, "timeline_remove": timeline_remove, "timeline_upload": timeline_upload, "timeline_fetch_start": timeline_fetch_start, "rgb_compare": rgb_compare, "meta": meta, "scene": scene_images, "analyze": analyze, "crop": crop, "review": review, "export": export,
        "fetch_start": fetch_start, "fetch_status": fetch_status, "upload": upload, "case": lambda a: case_card(a["case"], a.get("kind", "forest"), None, "")}


def handle(line, pool_out):
    rid = None
    try:
        req = json.loads(line); rid = req.get("id")
        args = dict(req.get("args") or {}); _owner.set(args.pop("_owner", None))
        msg = {"id": rid, "ok": True, "result": clean(CMDS[req["cmd"]](args))}
    except (ValueError, KeyError, TypeError) as e:
        msg = {"id": rid, "ok": False, "kind": "input", "error": str(e.args[0]) if e.args else str(e)}
    except Exception as e:
        traceback.print_exc(); msg = {"id": rid, "ok": False, "kind": "internal", "error": f"{type(e).__name__}: {e}"}
    with _lock:
        print(json.dumps(msg, allow_nan=False), file=_proto, flush=True)
    _slots.release()


def main():
    pool = ThreadPoolExecutor(max_workers=4)
    with _lock: print(json.dumps({"ready": True}), file=_proto, flush=True)
    for line in sys.stdin:
        if not line.strip(): continue
        if not _slots.acquire(blocking=False):           # bounded work: refuse instead of queueing without limit
            try: rid = json.loads(line).get("id")
            except Exception: rid = None
            with _lock: print(json.dumps({"id": rid, "ok": False, "kind": "busy", "error": "The satellite engine is busy. Try again in a moment."}), file=_proto, flush=True)
            continue
        pool.submit(handle, line.strip(), None)


if __name__ == "__main__":
    main()
