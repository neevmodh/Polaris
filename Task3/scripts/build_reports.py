"""Export both real case studies, their rasters and reproducible inference outputs."""
from pathlib import Path
import sys
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor.scenes import Scene
from monitor.analysis import forest_analysis, lake_analysis
from monitor.exports import bundle, json_text, png_bytes, rgb, overlay, geotiff_bytes
from monitor import water_model
from monitor.learning import baseline_forest_prior
from monitor.workspace import timeline_frame, timeline_key, region_records, reviewed_geojson, load_reviews, analysis_key

if __name__ == "__main__":
    for kind in ["forest", "lake"]:
        folder = ROOT / "data" / kind
        b, a = Scene.load(folder / "before.npz"), Scene.load(folder / "after.npz")
        target = ROOT / "outputs" / kind
        target.mkdir(parents=True, exist_ok=True)
        if kind == "forest":
            with np.load(folder / "reference.npz", allow_pickle=False) as z:
                prior = baseline_forest_prior(b, {k: z[k] for k in z.files})
            r = forest_analysis(b, a, model_path=ROOT / "models" / "forest_rf.joblib", forest_prior=prior)
            mask = r["loss"]
            arrays = {"ndvi_change": r["delta"], "ml_score": r["scores"], "loss_mask": np.where(r["valid"], mask.astype(float), np.nan)}
            table = r["alerts"]
            with np.load(ROOT / "models" / "sample_inference.npz") as z:
                rr, cc = np.where(z["holdout"])
                take = np.linspace(0, len(rr)-1, min(1000, len(rr)), dtype=int)
                rr, cc = rr[take], cc[take]
                samples = pd.DataFrame({"row": rr, "col": cc, "reference_loss": z["reference"][rr, cc],
                                        "ml_score": z["score"][rr, cc], "partition": "spatial_holdout"})
                samples.to_csv(target / "sample_inference.csv", index=False)
        else:
            prior = None
            wm = (water_model.segment(b), water_model.segment(a)) if water_model.available() else None
            r = lake_analysis(b, a, water_masks=wm)
            mask, table = r["alerts"], r["table"]
            arrays = {"ndci_change": r["delta"], "ndci_after": r["after"]["NDCI"],
                      "ndti_after": r["after"]["NDTI"], "water_mask": r["after"]["water"].astype(float)}
        (target / "summary.json").write_text(json_text(r["summary"]))
        table.to_csv(target / "indicators.csv", index=False)
        timeline_dir = ROOT / "data" / "timeline" / timeline_key(b, kind)
        extra_scenes = [Scene.load(p) for p in timeline_dir.glob("*.npz")]
        trend, _ = timeline_frame([b, *extra_scenes, a], kind, forest_prior=prior)
        trend.to_csv(target / "observation_timeline.csv", index=False)
        regions, groups = region_records(mask, a, r["delta"], r.get("scores"))
        decisions = load_reviews(ROOT / "data" / "reviews" / f"{analysis_key(b, a, mask)}.json")
        geo = reviewed_geojson(groups, a, regions, decisions)
        (target / "reviewed_regions.geojson").write_text(json_text(geo))
        extras = {"observation_timeline.csv": trend.to_csv(index=False), "reviewed_regions.geojson": json_text(geo)}
        (target / "analysis.zip").write_bytes(bundle(r["summary"], b, a, arrays, mask, r.get("metrics"), table.to_csv(index=False), extras))
        (target / "before.png").write_bytes(png_bytes(rgb(b)))
        (target / "after.png").write_bytes(png_bytes(rgb(a)))
        (target / "review_overlay.png").write_bytes(png_bytes(overlay(a, mask)))
        for name, arr in arrays.items():
            (target / f"{name}.tif").write_bytes(geotiff_bytes(arr.astype(np.float32), a))
        # An upload-ready raster uses our documented order and already-scaled reflectance.
        for label, scene in [("before", b), ("after", a)]:
            (target / f"{label}_8band.tif").write_bytes(geotiff_bytes(scene.data, scene))
        print(kind, json.dumps(r["summary"], indent=2), flush=True)
