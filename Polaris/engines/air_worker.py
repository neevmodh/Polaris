"""JSON-lines worker over Task 1 (Atmos): regional greenhouse-gas histories and trained forecasts.

Runs inside task1's own virtual environment with task1 as the working directory, so the website
reuses the same tested code the Streamlit app uses — no formula is reimplemented here.
"""
import json, math, os, sys, threading, traceback
from pathlib import Path

TASK1 = Path(os.environ.get("TASK1_DIR", Path(__file__).resolve().parents[2] / "task1")).resolve()
os.chdir(TASK1)
sys.path.insert(0, str(TASK1))
_proto = sys.stdout
sys.stdout = sys.stderr

import numpy as np, pandas as pd
from src.cities import anomalies, city_catalog, read_city
from src.data import GASES, validate_series
from src.forecast import HORIZONS, MODELS, forecast_view, train_and_forecast

_lock = threading.Lock()
_cache: dict = {}


def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, (np.floating, float)): return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.bool_): return bool(o)
    if isinstance(o, pd.Timestamp): return o.strftime("%Y-%m-%d")
    if isinstance(o, pd.DataFrame): return clean(o.to_dict(orient="records"))
    return o


def _station(code):
    code = str(code).upper()
    if code not in {c["station"] for c in city_catalog()}:
        raise ValueError(f"Unknown city {code!r}.")
    return code


def _analysis(code):
    """Training is the slow step, so each city is trained once per process."""
    with _lock:
        if code not in _cache:
            frame, info = read_city(code)
            _cache[code] = (frame, info, train_and_forecast(frame, 30))
        return _cache[code]


def meta(_):
    return {"cities": [{k: c[k] for k in ("name", "station", "latitude", "longitude", "unit", "origin",
                                          "scope", "grid_bounds", "last", "source_rows", "citation", "license", "url")}
                       for c in city_catalog()],
            "models": list(MODELS), "horizons": list(HORIZONS), "gases": GASES}


def forecast(a):
    code = _station(a.get("city", "NOIDA"))
    horizon = int(a.get("horizon", 14))
    if horizon not in HORIZONS: raise ValueError(f"horizon must be one of {list(HORIZONS)}")
    requested = a.get("model", "Auto (validation winner)")
    if requested != "Auto (validation winner)" and requested not in MODELS: raise ValueError("Unknown model.")
    frame, info, result = _analysis(code)
    view = forecast_view(result, horizon, requested)
    eval_h = min(HORIZONS, key=lambda h: abs(h - horizon))
    met = view["metrics"][view["metrics"].horizon_days == eval_h].sort_values("mae")
    sel = met[met.model == view["selected"]].iloc[0]
    persistence = float(met[met.model == "Persistence"].mae.iloc[0])
    quality = validate_series(frame)
    hist = frame.tail(180)
    return {
        "city": info["name"], "station": code, "unit": info["unit"], "gas": "co2",
        "selected": view["selected"], "horizon": horizon, "eval_horizon": eval_h,
        "latest": {"value": float(frame.value.iloc[-1]), "date": str(frame.date.max().date())},
        "final": {"value": float(view["forecast"].predicted.iloc[-1]), "date": str(view["forecast"].date.iloc[-1].date()),
                  "lower": float(view["forecast"].lower.iloc[-1]), "upper": float(view["forecast"].upper.iloc[-1])},
        "mae": float(sel.mae), "rmse": float(sel.rmse), "coverage": float(sel.coverage_90), "targets": int(sel.test_targets),
        "persistence_mae": persistence, "beats_persistence": bool(sel.mae < persistence),
        "skill_pct": float(100 * (1 - sel.mae / persistence)) if persistence else 0.0,
        "metrics": met[["model", "mae", "rmse", "coverage_90", "test_targets"]],
        "history": [{"date": str(d.date()), "value": float(v)} for d, v in zip(hist.date, hist.value)],
        "forecast": [{"date": str(d.date()), "predicted": float(p), "lower": float(lo), "upper": float(hi)}
                     for d, p, lo, hi in zip(view["forecast"].date, view["forecast"].predicted, view["forecast"].lower, view["forecast"].upper)],
        "importance": view["importance"].head(8),
        "split": view["split"], "coverage_pct": float(quality["coverage"] * 100),
        "first": str(quality["first"].date()), "last": str(quality["last"].date()),
        "scope": info["scope"], "origin": info["origin"], "citation": info["citation"], "grid_bounds": info["grid_bounds"],
    }


def alerts(a):
    code = _station(a.get("city", "NOIDA"))
    sigma = float(a.get("sigma", 2.5))
    if not 1.0 <= sigma <= 5.0: raise ValueError("sigma must be between 1 and 5")
    frame, info, _ = _analysis(code)
    flagged = anomalies(frame, sigma=sigma).tail(180)
    return {"unit": info["unit"], "city": info["name"], "sigma": sigma,
            "flagged": int(flagged.flag.sum()), "days": int(len(flagged)),
            "rows": [{"date": str(d.date()), "value": float(v), "level": None if pd.isna(lv) else float(lv), "flag": bool(f)}
                     for d, v, lv, f in zip(flagged.date, flagged.value, flagged.review_level, flagged.flag)]}


def compare(_):
    """Both cities at the same horizon, for the side-by-side sheet."""
    out = []
    for c in city_catalog():
        r = forecast({"city": c["station"], "horizon": 14})
        out.append({k: r[k] for k in ("city", "station", "unit", "selected", "latest", "final", "mae",
                                      "persistence_mae", "beats_persistence", "skill_pct", "coverage")})
    return {"cities": out, "horizon": 14}


CMDS = {"meta": meta, "forecast": forecast, "alerts": alerts, "compare": compare}


def main():
    print(json.dumps({"ready": True}), file=_proto, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        rid = None
        try:
            req = json.loads(line); rid = req.get("id")
            msg = {"id": rid, "ok": True, "result": clean(CMDS[req["cmd"]](req.get("args") or {}))}
        except (ValueError, KeyError, TypeError) as e:
            msg = {"id": rid, "ok": False, "kind": "input", "error": str(e.args[0]) if e.args else str(e)}
        except Exception as e:
            traceback.print_exc(); msg = {"id": rid, "ok": False, "kind": "internal", "error": f"{type(e).__name__}: {e}"}
        print(json.dumps(msg, allow_nan=False), file=_proto, flush=True)


if __name__ == "__main__":
    main()
