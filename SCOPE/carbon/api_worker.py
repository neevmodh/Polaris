"""Long-lived JSON-lines worker: the Next.js backend talks to this over stdin/stdout so the web app
reuses the exact tested Python engine (no duplicated formulas). One request per line, one reply per line."""
import json, math, os, sys, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
_proto = sys.stdout                       # protocol channel; everything else printed goes to stderr
sys.stdout = sys.stderr

import numpy as np, pandas as pd
from carbon import abatement as A, calculator as C, factors as F, runway as R, scope3 as S3

FUELS = {"diesel_l": "Diesel (L)", "petrol_l": "Petrol (L)", "lpg_kg": "LPG (kg)", "natural_gas_m3": "Natural gas (m³)"}


def clean(o):
    """Make numpy/pandas output strict-JSON safe (NaN/inf -> null)."""
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.bool_): return bool(o)
    if isinstance(o, pd.DataFrame): return clean(o.to_dict(orient="records"))
    return o


def models_ready(): return (ROOT / "models/model_s1.joblib").exists() and (ROOT / "models/model_s2.joblib").exists()


def meta(_):
    out = {"fuels": [{"key": k, "label": v, "ef": F.FUEL_EF[k]} for k, v in FUELS.items()],
           "scope3": [{"key": k, "label": v[1], "ghg": v[2], "naics": v[0], "ef_kg_per_usd": float(S3.load_useeio().loc[v[0]])} for k, v in S3.CATEGORIES.items()],
           "sigmas": {"fuel": F.FUEL_EF_SIGMA, "grid": F.GRID_EF_SIGMA, "spend": F.SPEND_EF_SIGMA},
           "grid_ef": F.GRID_EF_KG_PER_KWH, "usd_to_inr": F.USD_TO_INR, "models_ready": models_ready(),
           "data_source": (ROOT / "data/processed/DATA_SOURCE.txt").read_text().strip() if (ROOT / "data/processed/DATA_SOURCE.txt").exists() else "UNKNOWN"}
    if models_ready():
        from carbon.predict import _load
        b = _load("s1"); out.update(sectors=b["sectors"], activities=b["activities"], train_range=b["train_range"])
    return out


def _fuel(a): return {k: float(a.get(k, 0) or 0) for k in FUELS}


def calc(a):
    fuel, kwh, td = _fuel(a), float(a.get("kwh", 0) or 0), float(a.get("td_loss", 0) or 0)
    spend = {k: float(v) for k, v in (a.get("spend_inr") or {}).items() if v}
    fp = C.footprint(fuel, kwh, spend, td); mc = C.monte_carlo(fuel, kwh, spend, td_loss=td)
    return {"point": {"scope1": fp.scope1_t, "scope2": fp.scope2_t, "scope3": fp.scope3_t, "total": fp.total_t},
            "range": mc, "scope3_breakdown": S3.breakdown(spend) if spend else [],
            "drivers": C.drivers(fuel, kwh, spend, td_loss=td)}


def predict(a):
    from carbon.predict import predict as P
    return P(a["sector"], a["activity"], float(a["turnover_cr"]), (float(a["employees"]) if a.get("employees") else None),
             float(a.get("renewable_share", 0.1)), int(a.get("year", 2026)))


def abate(a):
    td = float(a.get("td_loss", 0) or 0)
    if a.get("from_ml"):
        s1, s2 = float(a["from_ml"]["s1_t"]), float(a["from_ml"]["s2_t"])
        d_l = s1 * 1000 / F.FUEL_EF["diesel_l"]; kwh = s2 * 1000 * (1 - td) / F.GRID_EF_KG_PER_KWH
    else:
        d_l, kwh = float(a.get("diesel_l", 0)), float(a.get("kwh", 0))
        s1, s2 = C.scope1({"diesel_l": d_l}), C.scope2(kwh, td_loss=td)
    s3 = float(a.get("s3_t", 0))
    lev = A.build_levers(d_l, kwh, s3, float(a.get("diesel_saved_frac", 0.268)), float(a.get("fuel_price", 80)),
                         float(a.get("solar_kwh", 0)), 3.5, 8.0, float(a.get("ppa_share", 0)), 0.5, float(a.get("supplier_cut", 0.1)))
    path = A.pathway(s1, s2, s3, lev, n=1500)
    m = A.macc(lev)
    return {"baseline": {"scope1": s1, "scope2": s2, "scope3": s3, "diesel_l": d_l, "kwh": kwh}, "macc": m, "pathway": path,
            "abated_2030_t": A.cumulative_abated(path, 2030), "abated_2050_t": A.cumulative_abated(path, 2050),
            "annual_net_cost_inr": float(m["annual_net_cost_inr"].sum()) if len(m) else 0.0}


def report(_):
    p = ROOT / "results/metrics.json"
    if not p.exists(): return {"ready": False}
    cmp_ = pd.read_csv(ROOT / "results/model_comparison.csv")
    return {"ready": True, "metrics": json.loads(p.read_text()), "comparison": cmp_,
            "plots": sorted(f.name for f in (ROOT / "results").glob("*.png"))}


def runway(a):
    return R.runway(float(a["stock_l"]), float(a["daily_l"]), int(a["delivery_day"]), float(a.get("cv", 0.15)),
                    float(a.get("saving_frac", 0)), int(a.get("delay_days", 0)))


def stress(_):
    p = ROOT / "results/stress.json"
    return json.loads(p.read_text()) if p.exists() else {"ready": False}


def _dispatch_file(key):
    if key not in ("polar", "community"): raise ValueError("profile must be 'polar' or 'community'")
    f = ROOT / "results" / "dispatch" / f"{key}.json"
    if not f.exists(): raise ValueError("Dispatch results are not generated yet. Run: python -m carbon.dispatch_eval")
    return json.loads(f.read_text())


def dispatch_summary(a):
    """Everything except the hourly weekly series (those are fetched one week at a time)."""
    out = {}
    for key in ("polar", "community"):
        f = ROOT / "results" / "dispatch" / f"{key}.json"
        if f.exists():
            d = json.loads(f.read_text()); d.pop("weeks", None); out[key] = d
    return {"ready": bool(out), "profiles": out}


def dispatch_week(a):
    d = _dispatch_file(a["profile"]); m = int(a["month"])
    if not 1 <= m <= 12: raise ValueError("month must be 1-12")
    return {sc: d["weeks"][sc][m - 1] for sc in ("A", "B", "C")}


CMDS = {"dispatch_summary": dispatch_summary, "dispatch_week": dispatch_week, "runway": runway, "stress": stress, "meta": meta, "calc": calc, "predict": predict, "abate": abate, "report": report}


def main():
    if models_ready():
        from carbon.predict import _load; _load("s1"); _load("s2")        # warm start
    print(json.dumps({"ready": True}), file=_proto, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        rid = None
        try:
            req = json.loads(line); rid = req.get("id")
            res = CMDS[req["cmd"]](req.get("args") or {})
            msg = {"id": rid, "ok": True, "result": clean(res)}
        except (ValueError, KeyError, TypeError) as e:
            msg = {"id": rid, "ok": False, "kind": "input", "error": str(e.args[0]) if e.args else str(e)}
        except Exception as e:
            traceback.print_exc(); msg = {"id": rid, "ok": False, "kind": "internal", "error": f"{type(e).__name__}: {e}"}
        print(json.dumps(msg, allow_nan=False), file=_proto, flush=True)


if __name__ == "__main__":
    main()
