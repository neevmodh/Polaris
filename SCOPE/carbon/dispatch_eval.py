"""Offline evaluation of the dispatch engine on a held-out year (2025). Writes results/dispatch/<profile>.json for the website and the tests.
Run:  python -m carbon.dispatch_eval [polar|community]    (about 30 minutes for both profiles)"""
import dataclasses, json, sys, time
from pathlib import Path
import numpy as np, pandas as pd
from carbon import forecast as F, microgrid as M, simulate as S, weather as W

OUT = Path(__file__).resolve().parents[1] / "results" / "dispatch"
YEAR_START, YEAR_DAYS = "2025-01-01", 357                     # forecasts look 168 h ahead, so the run stops a week before the data ends
WEEK_STARTS = [f"2025-{m:02d}-01" for m in range(1, 13)]
GREEN_WEEKS = ["2025-03-01", "2025-06-01", "2025-09-01", "2025-12-01"]
STRESS_START = {"polar": "2025-06-01", "community": "2025-01-05"}
STRESS_DAYS, DELIVERY_DAY = 26, 25


def r(a, nd=1): return [round(float(x), nd) for x in np.asarray(a)]


def week_slice(res: S.Result, start: str, hours=168):
    s = res.series.loc[pd.Timestamp(start): pd.Timestamp(start) + pd.Timedelta(hours=hours - 1)]
    return {"start": start, "demand": r(s.demand), "pv_used": r(s.pv_used), "wind_used": r(s.wind_used), "discharge": r(s.discharge), "charge": r(s.charge),
            "gen": r(s.gen), "soc": r(s.soc), "curtailed": r(s.curtailed), "fuel_l": r(s.fuel_l, 2), "unmet": r(s.unmet, 2)}


def monthly(res: S.Result):
    s = res.series; g = s.groupby(s.index.month)
    return {"fuel_l": r(g.fuel_l.sum()), "co2_t": r(g.fuel_l.sum() * 2.70 / 1000, 3), "renewable_used_kwh": r((g.pv_used.sum() + g.wind_used.sum())), "demand_kwh": r(g.demand.sum())}


def run_profile(key: str, log=print):
    p = M.PROFILES[key]; t0 = time.time()
    world = M.build_world(p, W.load_weather(p)); log(f"[{key}] weather loaded")
    f = F.Forecaster(world).fit(); fm = f.evaluate(); f.save(Path(__file__).resolve().parents[1] / "models" / "dispatch" / f"forecast_{key}.joblib")
    log(f"[{key}] forecaster trained ({time.time()-t0:.0f}s)")
    out = {"profile": dataclasses.asdict(p), "weather_source": "Open-Meteo archive (ERA5 reanalysis), 2020-2025, hourly UTC",
           "demand_source": "SIMULATED (heating-driven, daily and weekly pattern); replace with metered data",
           "split": {"train": "2020-2023", "calibration": "2024", "test": "2025"}, "forecast": fm, "scenarios": {}, "monthly": {}, "weeks": {}, "mode_compare": {}, "stress": {}}
    runs = {}
    for sc in ("A", "B", "C"):
        t = time.time(); res = S.simulate(world, f, sc, "economy", YEAR_START, YEAR_DAYS, replan_h=24); runs[sc] = res
        out["scenarios"][sc] = {**res.metrics, "name": S.SCENARIOS[sc], "solves": res.solves, "solve_seconds": round(res.solve_seconds, 1)}
        out["monthly"][sc] = monthly(res); out["weeks"][sc] = [week_slice(res, d) for d in WEEK_STARTS]
        log(f"[{key}] annual {sc}: fuel {res.metrics['fuel_l']:.0f} L, unmet {res.metrics['unmet_kwh']:.1f} kWh ({time.time()-t:.0f}s)")
    for d in GREEN_WEEKS:
        row = {}
        for mode in ("economy", "green"):
            res = S.simulate(world, f, "C", mode, d, 7, replan_h=24)
            row[mode] = {k: res.metrics[k] for k in ("fuel_l", "co2_t", "fuel_cost_inr", "generator_starts", "renewable_utilisation", "battery_throughput_kwh", "unmet_kwh")}
        a = S.simulate(world, f, "A", "economy", d, 7); row["A"] = {k: a.metrics[k] for k in ("fuel_l", "co2_t", "fuel_cost_inr", "generator_starts", "renewable_utilisation", "battery_throughput_kwh", "unmet_kwh")}
        out["mode_compare"][d] = row
    log(f"[{key}] mode comparison done")
    # resupply stress: the tank lasts about 20 days under rule-based operation, delivery comes on day 25
    st = STRESS_START[key]; a14 = S.simulate(world, f, "A", "economy", st, 14).metrics["fuel_l"] / 14
    tank = max(float(round(a14 * 20 / 50) * 50), 50.0); trajectories = {}
    for name, sc, mode in (("A", "A", "economy"), ("C-economy", "C", "economy"), ("C-survival", "C", "survival")):
        res = S.simulate(world, f, sc, mode, st, STRESS_DAYS, fuel0=tank, delivery_day=DELIVERY_DAY); b = res.series.iloc[:DELIVERY_DAY * 24]
        ess_un = np.maximum(b.unmet - (b.flex_served + (b.firm_served - p.essential_frac * b.demand).clip(lower=0)), 0)
        trajectories[name] = {"fuel_stock_daily": r(res.series.fuel_stock.iloc[::24] if len(res.series) else [], 0), "essential_unmet_daily_kwh": r(ess_un.groupby(np.arange(len(b)) // 24).sum(), 1),
                              "fuel_left_at_delivery_l": round(float(b.fuel_stock.iloc[-1]), 0), "unmet_kwh": round(float(b.unmet.sum()), 1), "essential_unmet_kwh": round(float(ess_un.sum()), 1),
                              "essential_unmet_pct": round(float(100 * ess_un.sum() / (p.essential_frac * b.demand.sum())), 2), "shed_nonessential_kwh": round(float(b.shed.sum()), 1),
                              "flex_shifted_kwh": round(res.metrics["flex_shifted_kwh"], 1),
                              "first_essential_unmet_day": (int(np.argmax(ess_un.values > 1e-6) / 24) + 1) if (ess_un > 1e-6).any() else None}
        log(f"[{key}] stress {name}: essential unmet {trajectories[name]['essential_unmet_kwh']} kWh, fuel left {trajectories[name]['fuel_left_at_delivery_l']} L")
    out["stress"] = {"start": st, "days": STRESS_DAYS, "delivery_day": DELIVERY_DAY, "tank_l": tank, "rule_based_daily_l": round(float(a14), 1), "scenarios": trajectories}
    out["generated_seconds"] = round(time.time() - t0)
    OUT.mkdir(parents=True, exist_ok=True); (OUT / f"{key}.json").write_text(json.dumps(out, allow_nan=False))
    log(f"[{key}] wrote results/dispatch/{key}.json in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    for k in (sys.argv[1:] or list(M.PROFILES)):
        run_profile(k)
