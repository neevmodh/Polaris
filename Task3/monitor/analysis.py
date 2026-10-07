from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from scipy.ndimage import label
from .indices import forest_screen, water_screen
from .learning import predict
from .scenes import assert_aligned


def finite_stat(a, fn=np.nanmedian):
    return float(fn(a)) if np.isfinite(a).any() else None


def forest_analysis(before, after, drop=0.2, vegetation=0.6, min_pixels=4, model_path=None, threshold=0.5, forest_prior=None):
    screened = forest_screen(before, after, drop, vegetation, min_pixels)
    if forest_prior is not None:
        if forest_prior.shape != before.shape:
            raise ValueError("Forest reference support must share the observation grid.")
        screened["eligible"] &= forest_prior
        # Apply the support first, then refilter patches to avoid counting tiny fragments.
        screened["loss"] &= forest_prior
        groups, _ = label(screened["loss"])
        sizes = np.bincount(groups.ravel())
        keep = sizes >= min_pixels
        keep[0] = False
        screened["loss"] = keep[groups]
    metrics, scores = None, None
    mask = screened["loss"]
    method = "NDVI screening baseline"
    if model_path is not None:
        model_path = Path(model_path)
        if not model_path.exists():
            raise ValueError("No trained forest model is available. Run scripts/train_forest.py first.")
        saved = joblib.load(model_path)  # Only the bundled, locally trained artifact; never accept uploads.
        scores = predict(saved["model"], before, after)
        mask = screened["eligible"] & (scores >= threshold)
        groups, _ = label(mask)
        sizes = np.bincount(groups.ravel())
        keep = sizes >= min_pixels
        keep[0] = False
        mask = keep[groups]
        method, metrics = "Trained random forest", saved["metrics"]
    area = before.pixel_area_m2 / 10000
    summary = {
        "analysis": "Forest-loss screening", "method": method,
        "region": before.metadata.get("region", "Custom region"),
        "observed_pair_pct": round(float(screened["valid"].mean()) * 100, 2),
        "observed_area_ha": round(float(screened["valid"].sum()) * area, 2),
        "baseline_vegetation_area_ha": round(float(screened["eligible"].sum()) * area, 2),
        "baseline_support": ("Hansen canopy2000 >=30%, no loss through baseline year, plus vegetation threshold; regrowth excluded"
                             if forest_prior is not None else "High baseline NDVI only; forest identity is not independently established"),
        "candidate_loss_area_ha": round(float(mask.sum()) * area, 2),
        "baseline_candidate_loss_area_ha": round(float(screened["loss"].sum()) * area, 2),
        "alert_regions": int(label(mask)[1]), "analysis_resolution_m": abs(before.transform.a),
        "mean_ndvi_change": finite_stat(screened["delta"], np.nanmean),
        "parameters": {"ndvi_drop": drop, "baseline_vegetation_ndvi": vegetation,
                       "minimum_patch_pixels": min_pixels, "rf_score_threshold": threshold},
        "interpretation": "Candidate tree-cover loss, not verified deforestation. Seasonal change, fire, drought, "
                          "harvest and reference-label errors can affect results. Baseline high NDVI does not prove forest. "
                          "Scores are uncalibrated. Validate alerts with reference maps and independent review.",
    }
    alerts = polygons_table(mask, before)
    return {**screened, "loss": mask, "scores": scores, "metrics": metrics, "summary": summary, "alerts": alerts}


def polygons_table(mask, scene):
    groups, count = label(mask)
    rows = []
    for i in range(1, count + 1):
        rr, cc = np.where(groups == i)
        x, y = scene.transform @ (float(cc.mean()) + 0.5, float(rr.mean()) + 0.5)
        rows.append({"region": i, "area_ha": round(len(rr) * scene.pixel_area_m2 / 10000, 2),
                     "centroid_x": round(x, 1), "centroid_y": round(y, 1), "status": "Review required"})
    return pd.DataFrame(rows, columns=["region", "area_ha", "centroid_x", "centroid_y", "status"]).sort_values("area_ha", ascending=False)


def lake_analysis(before, after, mndwi=0.0, algae_change=0.1, water_masks=None):
    assert_aligned(before, after)
    wb, wa = water_screen(before, mndwi), water_screen(after, mndwi)
    method = "SCL + spectral open-water mask"
    if water_masks is not None:
        from scipy.ndimage import binary_erosion
        for result, scene, wm in zip([wb, wa], [before, after], water_masks):
            # border_value=1: the scene edge is not a shoreline, so water touching it is kept
            result["water"] = binary_erosion(wm & scene.valid, iterations=1, border_value=1)
            # Recompute all indices for the ML-defined water support.
            from .indices import indices
            result.update({k: np.where(result["water"], v, np.nan) for k, v in indices(scene).items()})
        method = "Pretrained U-Net water segmentation + SCL quality mask"
    common = wb["water"] & wa["water"]
    if common.sum() < 10:
        raise ValueError("Too few common clear open-water pixels. Use another region or acquisition pair.")
    rows = []
    for key, title in [("NDCI", "Red-edge algae proxy"), ("NDTI", "Normalized turbidity proxy"),
                       ("visible_turbidity_ratio", "Visible-band turbidity ratio")]:
        a, b = np.where(common, wb[key], np.nan), np.where(common, wa[key], np.nan)
        v1, v2 = finite_stat(a), finite_stat(b)
        rows.append({"indicator": key, "meaning": title, "before_median": v1, "after_median": v2,
                     "change": v2 - v1 if v1 is not None and v2 is not None else None,
                     "units": "unitless spectral proxy"})
    delta = np.where(common, wa["NDCI"] - wb["NDCI"], np.nan)
    alerts = common & (delta > algae_change)
    area = before.pixel_area_m2 / 10000
    summary = {"analysis": "Lake water-quality screening", "method": method,
               "region": before.metadata.get("region", "Custom region"),
               "before_open_water_ha": round(float(wb["water"].sum()) * area, 2),
               "after_open_water_ha": round(float(wa["water"].sum()) * area, 2),
               "common_water_ha": round(float(common.sum()) * area, 2),
               "algae_proxy_increase_ha": round(float(alerts.sum()) * area, 2),
               "observed_pair_pct": round(float((before.valid & after.valid).mean()) * 100, 2),
               "parameters": {"mndwi": mndwi, "algae_proxy_increase": algae_change},
               "indicators": rows,
               "interpretation": "Unitless indicators of optical change in clear open water; not measured chlorophyll, "
                                 "turbidity in NTU, pathogens, sewage, heavy metals or drinking-water safety. "
                                 "Field sampling and local calibration are required. Atmospheric correction, sun glint, "
                                 "shallow bottoms and floating vegetation can affect results. Shoreline pixels are eroded.",
               "comparison_support": "Same clear, open-water pixels at both dates; water areas include only observed eroded mask."}
    return {"before": wb, "after": wa, "common": common, "delta": delta,
            "alerts": alerts, "summary": summary, "table": pd.DataFrame(rows)}
