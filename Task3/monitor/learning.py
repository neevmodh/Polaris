"""Train an interpretable forest-loss classifier with a spatial holdout.

This is a new small random-forest baseline; it does not claim to run Forest-CD.
Hansen labels are external map references, not field-verified ground truth.
"""
from pathlib import Path
import json
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, f1_score, jaccard_score, average_precision_score, confusion_matrix
from .indices import indices
from .scenes import assert_aligned


def features(before, after):
    assert_aligned(before, after)
    ib, ia = indices(before), indices(after)
    arrays, names = [], []
    for key in ["NDVI", "NBR", "NDMI", "MNDWI"]:
        for suffix, values in [("before", ib[key]), ("after", ia[key]), ("delta", ia[key] - ib[key])]:
            arrays.append(values)
            names.append(f"{key}_{suffix}")
    for band in ["red", "nir", "swir16", "swir22"]:
        arrays.append(after.band(band) - before.band(band))
        names.append(f"{band}_delta")
    X = np.stack(arrays, axis=-1)
    return X, names


def reference_labels(before, after, reference):
    start = int(before.metadata["datetime"][:4]) - 2000
    end = int(after.metadata["datetime"][:4]) - 2000
    ly = reference["lossyear"]
    if end > 24 or start < 0 or start >= end:
        raise ValueError("The reference covers 2001–2024; use distinct baseline/comparison years within that range.")
    # Discard endpoint years: annual labels cannot say whether a loss preceded acquisition.
    usable = (reference["datamask"] == 1) & (reference["treecover2000"] >= 30)
    usable &= ((ly == 0) | (ly > start)) & (ly != start) & (ly != end)
    y = ((ly > start) & (ly < end)).astype(np.uint8)
    return y, usable


def baseline_forest_prior(before, reference):
    """Conservative forest support: historical canopy with no loss through baseline year.

    Annual endpoint ambiguity and regrowth are excluded rather than guessed.
    """
    start = int(before.metadata["datetime"][:4]) - 2000
    ly = reference["lossyear"]
    return (reference["datamask"] == 1) & (reference["treecover2000"] >= 30) & ((ly == 0) | (ly > start))


def score(y, p, threshold=0.5):
    pred = p >= threshold
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {"precision": float(precision_score(y, pred, zero_division=0)),
            "recall": float(recall_score(y, pred, zero_division=0)),
            "f1": float(f1_score(y, pred, zero_division=0)),
            "iou": float(jaccard_score(y, pred, zero_division=0)),
            "average_precision": float(average_precision_score(y, p)),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}


def train(before, after, reference, outdir):
    X, names = features(before, after)
    y, usable = reference_labels(before, after, reference)
    usable &= before.valid & after.valid & np.isfinite(X).all(axis=-1)
    h, w = before.shape
    cols = np.indices((h, w))[1]
    # Fixed geographic split with a 3-pixel gap; never select holdout based on scores.
    train_mask = usable & (cols < int(w * 0.7) - 3)
    test_mask = usable & (cols >= int(w * 0.7) + 3)
    for name, mask in [("training", train_mask), ("holdout", test_mask)]:
        counts = np.bincount(y[mask], minlength=2)
        if counts.min() < 20:
            raise ValueError(f"Insufficient {name} reference examples ({counts.tolist()}). Choose a larger forest region.")
    rng = np.random.default_rng(42)
    xt, yt = X[train_mask], y[train_mask]
    if len(yt) > 40000:
        take = rng.choice(len(yt), 40000, replace=False)
        xt, yt = xt[take], yt[take]
    model = RandomForestClassifier(n_estimators=160, max_depth=14, min_samples_leaf=8,
                                   class_weight="balanced_subsample", random_state=42, n_jobs=2)
    model.fit(xt, yt)
    p = model.predict_proba(X[test_mask])[:, 1]
    ib, ia = indices(before), indices(after)
    baseline = ((ib["NDVI"] >= 0.6) & ((ia["NDVI"] - ib["NDVI"]) < -0.2))[test_mask]
    metrics = {"model": "Random forest · 160 trees · seed 42", "features": names,
               "trained_samples": int(len(yt)), "holdout_samples": int(test_mask.sum()),
               "holdout_positive_samples": int(y[test_mask].sum()),
               "training_positive_samples": int(yt.sum()),
               "spatial_split": "West 70% train; east 30% holdout; 6-column gap",
               "holdout_bounds": "Eastern strip of the same scene pair; not external geographic or temporal validation",
               "reference": "Hansen GFC 2024 v1.12; canopy2000 >=30%; endpoint loss years excluded",
               "label_interval": f"{int(before.metadata['datetime'][:4])+1}–{int(after.metadata['datetime'][:4])-1}",
               "rf": score(y[test_mask], p), "ndvi_baseline": score(y[test_mask], baseline.astype(float)),
               "feature_importance": dict(zip(names, map(float, model.feature_importances_))),
               "probability_note": "Model scores are not calibrated probabilities or confidence intervals.",
               "scene_ids": [before.metadata["id"], after.metadata["id"]]}
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": names, "metrics": metrics}, outdir / "forest_rf.joblib")
    (outdir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    prediction = predict(model, before, after)
    np.savez_compressed(outdir / "sample_inference.npz", score=prediction, holdout=test_mask,
                        training=train_mask, reference=y, reference_valid=usable)
    return model, metrics


def predict(model, before, after):
    X, _ = features(before, after)
    valid = before.valid & after.valid & np.isfinite(X).all(axis=-1)
    out = np.full(before.shape, np.nan, dtype=np.float32)
    if valid.any():
        out[valid] = model.predict_proba(X[valid])[:, 1]
    return out
