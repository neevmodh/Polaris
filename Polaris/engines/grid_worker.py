"""JSON-lines worker over the NetZeroAI microgrid project: renewable forecasts and optimal dispatch.

Runs inside netzero-ai's virtual environment with that project as the working directory, so the
website reuses its tested XGBoost forecasts and Pyomo/HiGHS optimiser unchanged.
"""
import json, math, os, sys, threading, traceback
from pathlib import Path

GRID = Path(os.environ.get("NETZERO_DIR", Path(__file__).resolve().parents[2] / "netzero-ai")).resolve()
os.chdir(GRID)
sys.path.insert(0, str(GRID))
_proto = sys.stdout
sys.stdout = sys.stderr

import numpy as np, pandas as pd, yaml
from src.optimization.model import kpis, optimize_dispatch
from src.simulation.scenarios import SCENARIOS, run_scenario

CFG = yaml.safe_load(open("configs/config.yaml"))
DATA = GRID / "data/processed/master_hourly.csv"
_lock = threading.Lock()
_cache: dict = {}


def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, (np.floating, float)): return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.bool_): return bool(o)
    if isinstance(o, pd.Timestamp): return o.isoformat()
    if isinstance(o, pd.DataFrame): return clean(o.to_dict(orient="records"))
    return o


def _history():
    if not DATA.exists():
        raise ValueError("The microgrid dataset is missing. Run: python -m src.data.generate_demo_data")
    return pd.read_csv(DATA, parse_dates=["timestamp"])


def _priced(df):
    """Time-of-day tariff and grid carbon intensity, the same shape the project's API uses."""
    out = df.copy()
    out["grid_price_rs_kwh"] = out.timestamp.dt.hour.map(lambda h: 11 if 18 <= h <= 22 else (5.5 if 10 <= h <= 16 else 7.5))
    out["grid_carbon_kgco2_kwh"] = out.timestamp.dt.hour.map(lambda h: .9 if 18 <= h <= 22 else .65)
    return out


def _forecast(hours):
    with _lock:
        if hours not in _cache:
            df = _history()
            trained = all((GRID / f"models/{x}_xgb.joblib").exists() for x in ("solar_available_kw", "wind_available_kw", "load_kw"))
            if trained:
                from src.forecasting.predict import forecast_all
                out = forecast_all(df.tail(200), hours)
            else:                                      # untrained checkout: repeat the last hour so the page still works
                last = df.tail(1)
                out = pd.concat([last] * hours, ignore_index=True)
                out["timestamp"] = [last.timestamp.iloc[0] + pd.Timedelta(hours=i + 1) for i in range(hours)]
            _cache[hours] = (_priced(out), trained)
        return _cache[hours]


def _plan(f):
    d = optimize_dispatch(f, CFG)
    return {"kpis": kpis(f, d), "method": d.attrs.get("method"), "fallback_reason": d.attrs.get("fallback_reason"),
            "dispatch": [{"timestamp": r.timestamp.isoformat(), "solar_kw": float(r.solar_kw), "wind_kw": float(r.wind_kw),
                          "charge_kw": float(r.charge_kw), "discharge_kw": float(r.discharge_kw), "grid_import_kw": float(r.grid_import_kw),
                          "curtail_kw": float(r.curtail_kw), "unserved_kw": float(r.unserved_kw), "soc_pct": float(r.soc) * 100}
                         for r in d.itertuples()]}


def meta(_):
    m = GRID / "models/metrics.json"
    return {"scenarios": list(SCENARIOS), "config": {k: CFG[k] for k in ("plant", "battery", "grid")},
            "accuracy": json.loads(m.read_text(encoding="utf-8")) if m.exists() else {},
            "data_ready": DATA.exists(), "models_ready": all((GRID / f"models/{x}_xgb.joblib").exists()
                                                             for x in ("solar_available_kw", "wind_available_kw", "load_kw"))}


def plan(a):
    """The optimal day, plus the forecast it was planned against."""
    hours = int(a.get("hours", 24))
    if not 6 <= hours <= 48: raise ValueError("hours must be between 6 and 48")
    name = a.get("scenario") or ""
    f, trained = _forecast(hours)
    if name:
        if name not in SCENARIOS: raise ValueError(f"Unknown scenario. Choose one of: {', '.join(SCENARIOS)}")
        r = run_scenario(f, CFG, name)
        x = r.pop("dispatch")
        out = {**r, "dispatch": [{"timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
                                  **{k: float(row[k]) for k in ("solar_kw", "wind_kw", "charge_kw", "discharge_kw", "grid_import_kw", "curtail_kw", "unserved_kw")},
                                  "soc_pct": float(row["soc"]) * 100} for row in x]}
    else:
        out = {"scenario": "normal", **_plan(f)}
    out["forecast"] = [{"timestamp": t.isoformat(), "solar_kw": float(s), "wind_kw": float(w), "load_kw": float(l),
                        "price": float(p), "carbon": float(c)}
                       for t, s, w, l, p, c in zip(f.timestamp, f.solar_available_kw, f.wind_available_kw, f.load_kw,
                                                   f.grid_price_rs_kwh, f.grid_carbon_kgco2_kwh)]
    out["forecast_is_trained"] = trained
    return out


def compare(a):
    """Every disturbance against the ordinary day: the table that shows what planning is worth."""
    hours = int(a.get("hours", 24))
    f, _ = _forecast(hours)
    rows = [{"scenario": "normal", **{k: v for k, v in _plan(f).items() if k != "dispatch"}}]
    for name in SCENARIOS:
        r = run_scenario(f, CFG, name)
        rows.append({"scenario": name, "kpis": r["kpis"], "method": r["method"], "fallback_reason": r["fallback_reason"]})
    return {"rows": rows}


CMDS = {"meta": meta, "plan": plan, "compare": compare}


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
