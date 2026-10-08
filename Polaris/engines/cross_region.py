"""Out-of-region check of Task 3's forest model: score the model trained on Rondonia on other places it has never seen.
Uses Task3's public functions only (read-only). Writes Polaris/data/validation/cross_region.json.
Run with Task3's interpreter:  ../Task3/.venv/bin/python engines/cross_region.py"""
import json, sys, time, traceback
from pathlib import Path
import joblib, numpy as np

HERE = Path(__file__).resolve().parents[1]
TASK3 = HERE.parent / "Task3"
sys.path.insert(0, str(TASK3))
from monitor.catalog import fetch_pair, hansen_reference
from monitor.indices import indices
from monitor.learning import features, reference_labels, score
from monitor.scenes import utm_grid

OUT = HERE / "data" / "validation"; OUT.mkdir(parents=True, exist_ok=True)
REGIONS = [  # name, bbox, before range, after range (same season logic as the training pair)
    ("Rondonia east (same state, 120 km away)", [-63.40, -9.50, -63.32, -9.42], ["2019-07-01", "2019-09-30"], ["2024-07-01", "2024-09-30"]),
    ("Mato Grosso north (different Amazon state)", [-55.80, -10.95, -55.72, -10.87], ["2019-06-01", "2019-09-30"], ["2024-06-01", "2024-09-30"]),
    ("Riau, Sumatra (different continent and climate)", [102.00, 0.50, 102.08, 0.58], ["2019-02-01", "2019-09-30"], ["2024-02-01", "2024-09-30"]),
    ("Para, Brazil (the arc of deforestation)", [-55.30, -7.00, -55.22, -6.92], ["2019-06-01", "2019-09-30"], ["2024-06-01", "2024-09-30"]),
    ("Santa Cruz, Bolivia (transition forest)", [-61.60, -16.60, -61.52, -16.52], ["2019-06-01", "2019-09-30"], ["2024-06-01", "2024-09-30"]),
    ("Gran Chaco, Paraguay (dry forest)", [-59.90, -21.60, -59.82, -21.52], ["2019-06-01", "2019-09-30"], ["2024-06-01", "2024-09-30"]),
]


def evaluate(name, bbox, b_rng, a_rng):
    folder = OUT / ("r_" + "".join(c if c.isalnum() else "_" for c in name)[:28])
    t0 = time.time()
    if (folder / "before.npz").exists() and (folder / "after.npz").exists():
        from monitor.scenes import Scene
        before, after = Scene.load(folder / "before.npz"), Scene.load(folder / "after.npz")
    else:
        before, after = fetch_pair(bbox, b_rng, a_rng, folder, log=lambda s: None)
        for lab, s in (("before", before), ("after", after)): s.save(folder / f"{lab}.npz")
    ref_path = folder / "reference.npz"
    if ref_path.exists():
        z = np.load(ref_path); ref = {k: z[k] for k in z.files}
    else:
        ref = hansen_reference(bbox, utm_grid(bbox), folder)
    y, usable = reference_labels(before, after, ref)
    X, names = features(before, after)
    usable = usable & before.valid & after.valid & np.isfinite(X).all(axis=-1)
    n, pos = int(usable.sum()), int(y[usable].sum())
    if n < 500 or pos < 20:
        return {"name": name, "bbox": bbox, "status": "too little reference loss to score", "usable_pixels": n, "loss_pixels": pos,
                "scenes": [before.metadata["id"], after.metadata["id"]]}
    saved = joblib.load(TASK3 / "models" / "forest_rf.joblib")
    p = saved["model"].predict_proba(X[usable])[:, 1]
    ib, ia = indices(before), indices(after)
    base = ((ib["NDVI"] >= 0.6) & ((ia["NDVI"] - ib["NDVI"]) < -0.2))[usable].astype(float)
    return {"name": name, "bbox": bbox, "status": "scored", "usable_pixels": n, "loss_pixels": pos, "loss_rate": round(pos / n, 4),
            "random_forest": score(y[usable], p), "ndvi_baseline": score(y[usable], base), "scenes": [before.metadata["id"], after.metadata["id"]],
            "dates": [before.metadata["datetime"][:10], after.metadata["datetime"][:10]], "seconds": round(time.time() - t0)}


if __name__ == "__main__":
    results = []
    for r in REGIONS:
        try:
            res = evaluate(*r)
        except Exception as exc:                       # an unusable region is a result too: say why
            traceback.print_exc(); res = {"name": r[0], "bbox": r[1], "status": f"could not be evaluated: {str(exc)[:160]}"}
        print(json.dumps({k: v for k, v in res.items() if k not in ("random_forest", "ndvi_baseline")}), flush=True)
        if res.get("status") == "scored":
            print("   RF  F1 %.3f P %.3f R %.3f AP %.3f | NDVI F1 %.3f P %.3f R %.3f" % (res["random_forest"]["f1"], res["random_forest"]["precision"], res["random_forest"]["recall"], res["random_forest"]["average_precision"], res["ndvi_baseline"]["f1"], res["ndvi_baseline"]["precision"], res["ndvi_baseline"]["recall"]), flush=True)
        results.append(res)
    saved = json.loads((TASK3 / "models" / "metrics.json").read_text(encoding="utf-8"))
    (OUT / "cross_region.json").write_text(json.dumps({"in_region_holdout": {"rf": {k: saved["rf"][k] for k in ("precision", "recall", "f1", "iou", "average_precision")},
        "ndvi_baseline": {k: saved["ndvi_baseline"][k] for k in ("precision", "recall", "f1", "iou", "average_precision")}, "note": saved["holdout_bounds"]},
        "regions": results, "model": saved["model"], "trained_on": "Rondonia 2019 -> 2024 western 70%"}, indent=2))
    print("wrote", OUT / "cross_region.json")
