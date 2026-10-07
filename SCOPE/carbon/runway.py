"""Fuel runway planner (Polaris link): will the diesel last until the next delivery?
Illustrative stochastic model, NOT a weather forecast: daily use is lognormal around a mean with persistence (cold spells),
using common random numbers so scenarios are directly comparable."""
import numpy as np
from carbon import factors as F

HORIZON_PAD = 40
RHO = 0.7            # day-to-day persistence of consumption anomalies (assumption)


def _check(name, v, lo, hi):
    if not (np.isfinite(v) and lo <= v <= hi): raise ValueError(f"{name} must be between {lo} and {hi}, got {v!r}")
    return float(v)


def runway(stock_l, daily_l, delivery_day, cv=0.15, saving_frac=0.0, delay_days=0, n=4000, seed=42, target_p=0.95):
    stock = _check("stock_l", stock_l, 1, 1e8); daily = _check("daily_l", daily_l, 0.1, 1e7)
    day = int(_check("delivery_day", delivery_day, 1, 365)); cv = _check("cv", cv, 0, 1.0)
    save = _check("saving_frac", saving_frac, 0, 0.9); delay = int(_check("delay_days", delay_days, 0, 60))
    max_delay = 14
    H = day + max(delay, max_delay) + HORIZON_PAD
    rng = np.random.default_rng(seed)
    sig = np.sqrt(np.log(1 + cv ** 2))
    x = np.zeros((n, H)); x[:, 0] = rng.standard_normal(n)
    e = rng.standard_normal((n, H))
    for t in range(1, H): x[:, t] = RHO * x[:, t - 1] + np.sqrt(1 - RHO ** 2) * e[:, t]
    base = daily * np.exp(sig * x - sig ** 2 / 2)                      # litres per day, mean = daily

    def cum(s): return np.cumsum(base * (1 - s), axis=1)
    def runway_days(c): return (c <= stock).sum(axis=1)               # whole days fully covered
    def p_ok(c, d): return float(np.mean(c[:, d - 1] <= stock))        # fuel lasts through day d

    c0, c1 = cum(0.0), cum(save)
    r0, r1 = runway_days(c0), runway_days(c1)
    q = lambda a: [float(v) for v in np.percentile(a, [10, 50, 90])]
    # smallest saving that reaches the target probability at the (possibly delayed) delivery
    need_day = day + delay
    lo, hi, needed = 0.0, 0.9, None
    if p_ok(cum(0.9), need_day) >= target_p:
        if p_ok(c0, need_day) >= target_p:
            needed = 0.0
        else:
            for _ in range(30):
                mid = (lo + hi) / 2
                if p_ok(cum(mid), need_day) >= target_p: hi = mid
                else: lo = mid
            needed = hi
    delays = list(range(0, max_delay + 1))
    by_day = lambda c: [float(np.mean(c[:, day + d - 1] <= stock)) for d in delays]
    ef = F.FUEL_EF["diesel_l"]
    use0, use1 = float(np.mean(c0[:, day - 1])), float(np.mean(c1[:, day - 1]))
    return {
        "inputs": {"stock_l": stock, "daily_l": daily, "delivery_day": day, "cv": cv, "saving_frac": save, "delay_days": delay},
        "nominal_runway_days": stock / daily,
        "runway_days": {"baseline": q(r0), "with_saving": q(r1)},
        "p_ok_at_delivery": {"baseline": p_ok(c0, day), "with_saving": p_ok(c1, day)},
        "p_ok_with_delay": {"baseline": p_ok(c0, need_day), "with_saving": p_ok(c1, need_day)},
        "delay_curve": {"delays": delays, "baseline": by_day(c0), "with_saving": by_day(c1)},
        "saving_needed_for_target": needed, "target_p": target_p,
        "diesel_to_delivery_l": {"baseline": use0, "with_saving": use1},
        "co2_to_delivery_t": {"baseline": use0 * ef / 1000, "with_saving": use1 * ef / 1000},
        "gap_days_median": float(day - np.median(r0)),
        "assumptions": f"daily use lognormal, CV {cv:.0%}, day-to-day persistence {RHO}; not a weather forecast",
    }
