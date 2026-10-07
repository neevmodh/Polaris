"""Rolling-horizon operation of a microgrid: three ways to run the same hardware against the same real weather.
A  rule-based: renewables first, battery down to an operator reserve, then the generator follows the load.
B  optimizer fed with simple forecasts (same hour yesterday).
C  optimizer fed with the trained LightGBM forecasts (Survival mode uses a conservative band).
Plans are made from forecasts available at the planning time; outcomes are scored on what actually happened."""
from dataclasses import dataclass, field
import time
import numpy as np, pandas as pd
from carbon.microgrid import Profile, World
from carbon import milp

SCENARIOS = {"A": "Rule-based operation", "B": "Optimizer + simple forecasts", "C": "Optimizer + trained forecasts"}
RULE_SOC_MIN = 0.40          # a common operator rule: do not take the battery below 40%; assumption, shown in the interface


@dataclass
class State:
    soc: float; fuel: float; on: int = 0


@dataclass
class Result:
    scenario: str; mode: str; profile: str; start: str; days: int
    series: pd.DataFrame; metrics: dict; solves: int = 0; solve_seconds: float = 0.0; notes: list = field(default_factory=list)


def _step(p: Profile, st: State, firm, flex_served, pv_av, wind_av, g_plan, soc_floor_frac):
    Gmax, Gmin, Pb, E = p.gen_kw, p.gen_min_kw, p.battery_kw, p.battery_kwh
    load = firm + flex_served; re = pv_av + wind_av
    floor = soc_floor_frac * E; usable = max(st.soc - floor, 0.0) * p.eta_d
    g = float(np.clip(g_plan, Gmin, Gmax)) if (g_plan > 1e-9 and st.fuel > 0) else 0.0
    net = load - re - g; d = c = 0.0
    if net > 1e-9:
        if usable >= net or st.fuel <= 0 or g > 0:
            d = min(net, Pb, usable); net -= d
            if net > 1e-9 and st.fuel > 0 and g == 0:
                g = min(Gmax, max(Gmin, net)); net -= g
        else:
            g = min(Gmax, max(Gmin, net)); net -= g
            if net > 1e-9:
                d = min(net, Pb, usable); net -= d
    unmet = max(net, 0.0)
    if net < -1e-9:
        c = min(-net, Pb, (p.soc_max * E - st.soc) / p.eta_c)
        rem = -net - c
    else:
        rem = 0.0
    if c > 1e-9 and d > 1e-9:
        m = min(c, d); c -= m; d -= m
    re_cur = min(rem, re); dump = rem - re_cur
    pv_cur = re_cur * (pv_av / re) if re > 1e-12 else 0.0
    fuel_l = (p.fuel_a * g + p.fuel_b * Gmax) if g > 0 else 0.0
    if fuel_l > st.fuel + 1e-9:                      # not enough diesel left: the generator cannot run this hour
        unmet += g; g = 0.0; fuel_l = 0.0
    st.soc = float(np.clip(st.soc + p.eta_c * c - d / p.eta_d, p.soc_min * E - 1e-6, p.soc_max * E + 1e-6))
    st.fuel -= fuel_l; started = int(g > 0 and not st.on); st.on = int(g > 0)
    return dict(gen=g, fuel_l=fuel_l, charge=c, discharge=d, unmet=unmet, pv_used=pv_av - pv_cur, wind_used=wind_av - (re_cur - pv_cur),
                curtailed=re_cur + dump, dump=dump, soc=st.soc, fuel_stock=st.fuel, start=started)


def _adjust_setpoint(p: Profile, plan, k, dem_f, pv_f, wind_f, dem_a, flex_served, firm_act, re_actual, ess_frac, norm_frac):
    """The plan commits the generator; its output follows the forecast error so the planned battery flow still holds.
    Shortfalls are first absorbed by renewable energy the plan had chosen to curtail; surplus above the forecast lowers the output."""
    if plan.g[k] <= 1e-9: return 0.0
    re_f = pv_f + wind_f; re_used = plan.pv_used[k] + plan.wind_used[k]; cur_plan = max(re_f - re_used, 0.0)
    d_re = re_actual - re_f
    d_eff = d_re if d_re > 0 else min(d_re + cur_plan, 0.0)
    load_plan = (ess_frac + norm_frac) * dem_f - plan.shed[k] + plan.flex[k]; load_act = firm_act + flex_served
    g = plan.g[k] + (load_act - load_plan) - d_eff
    if g < 0.5 * p.gen_min_kw: return 0.0
    return float(min(max(g, p.gen_min_kw), p.gen_kw))


def simulate(world: World, forecaster, scenario="C", mode="economy", start="2025-01-01", days=7, replan_h=24, horizon=168, fuel0=None,
             delivery_day=None, progress=None) -> Result:
    p = world.profile; i0 = world.idx(start); n = int(days * 24)
    if i0 + n + horizon > len(world.times) - 1 and scenario != "A":
        raise ValueError("The simulation window must end at least a week before the weather data does (forecasts look 168 hours ahead).")
    st = State(soc=0.6 * p.battery_kwh, fuel=float(p.tank_l if fuel0 is None else fuel0))
    rows, solves, secs = [], 0, 0.0
    flex_frac, ess_frac, norm_frac = p.flexible_frac, p.essential_frac, p.normal_frac; firm_frac = 1 - flex_frac
    for k0 in range(0, n, replan_h):
        i = i0 + k0; steps = min(replan_h, n - k0)
        plan = None
        if scenario in ("B", "C"):
            fc = forecaster.predict(i, "seasonal_naive" if scenario == "B" else "lightgbm", band="conservative" if (scenario == "C" and mode == "survival") else None)
            H = min(horizon, len(world.times) - 1 - i)
            dem = fc["demand"][:H]; pv = fc["solar_cf"][:H] * p.pv_kwp; wd = fc["wind_cf"][:H] * p.wind_kw
            budget = None
            if mode == "survival" and delivery_day is not None:
                left_h = max(delivery_day * 24 - k0, 24)
                budget = 0.97 * st.fuel * min(H, left_h) / left_h
            t0 = time.time()
            plan = milp.solve_window(p, ess_frac * dem, norm_frac * dem, flex_frac * dem, pv, wd, st.soc, mode=mode, fuel_stock_l=st.fuel, fuel_budget_l=budget, prev_on=st.on,
                                     soc_end_frac=0.7 if mode == "survival" else None, flex_curtail_frac=1.0 if mode == "survival" else 0.0)
            secs += time.time() - t0; solves += 1
            planned_dem = dem
        for k in range(steps):
            j = i + k; D = float(world.demand[j]); firm, flex_base = firm_frac * D, flex_frac * D
            if plan is not None:
                scale = np.clip(D / max(planned_dem[k], 1e-6), 0.5, 2.0)
                flex_served = float(plan.flex[k]) * scale; floor = p.soc_min
                shed = min(float(plan.shed[k]) * scale, norm_frac * D)
                firm = ess_frac * D + norm_frac * D - shed
                g_cmd = _adjust_setpoint(p, plan, k, planned_dem[k], pv[k], wd[k], D, flex_served, firm, float(world.pv[j] + world.wind[j]), ess_frac, norm_frac)
            else:
                flex_served, g_cmd, floor, shed = flex_base, 0.0, RULE_SOC_MIN, 0.0
            out = _step(p, st, firm, flex_served, float(world.pv[j]), float(world.wind[j]), g_cmd, floor)
            rows.append(dict(time=world.times[j], demand=D, flex_base=flex_base, flex_served=flex_served, shed=shed, firm_served=firm, pv_avail=float(world.pv[j]), wind_avail=float(world.wind[j]), **out))
        if progress: progress(min(k0 + steps, n) / n)
    s = pd.DataFrame(rows).set_index("time")
    return Result(scenario, mode, p.key, start, days, s, metrics_of(p, s, world, i0, n), solves, secs)


def metrics_of(p: Profile, s: pd.DataFrame, world: World, i0: int, n: int) -> dict:
    re_av = float((s.pv_avail + s.wind_avail).sum()); re_used = float((s.pv_used + s.wind_used).sum()); load = float((s.demand - 0).sum())
    daily = s.fuel_l.resample("D").sum()
    return {"fuel_l": float(s.fuel_l.sum()), "co2_t": float(s.fuel_l.sum() * milp.CO2_KG_PER_L / 1000), "fuel_cost_inr": float(s.fuel_l.sum() * p.fuel_price),
            "generator_starts": int(s.start.sum()), "generator_hours": int((s.gen > 0).sum()), "generator_kwh": float(s.gen.sum()),
            "renewable_available_kwh": re_av, "renewable_used_kwh": re_used, "renewable_utilisation": re_used / re_av if re_av > 0 else None,
            "curtailed_kwh": float(s.curtailed.sum()), "battery_throughput_kwh": float((s.charge + s.discharge).sum()),
            "demand_kwh": load, "unmet_kwh": float(s.unmet.sum()),
            "unmet_essential_kwh": float(np.maximum(s.unmet - (s.flex_served + (s.firm_served - p.essential_frac * s.demand).clip(lower=0)), 0).sum()),
            "shed_nonessential_kwh": float(s.shed.sum()),
            "essential_served_pct": float(100 * (1 - np.maximum(s.unmet - (s.flex_served + (s.firm_served - p.essential_frac * s.demand).clip(lower=0)), 0).sum() / max((p.essential_frac * s.demand).sum(), 1e-9))), "unmet_pct": float(100 * s.unmet.sum() / max(load, 1e-9)),
            "flex_shifted_kwh": float((s.flex_served - s.flex_base).abs().sum() / 2), "min_fuel_stock_l": float(s.fuel_stock.min()),
            "first_unmet_day": (int((s.unmet > 1e-6).values.argmax() / 24) + 1) if (s.unmet > 1e-6).any() else None,
            "daily_fuel_l_p50": float(daily.median()), "daily_fuel_l_p90": float(daily.quantile(0.9)), "daily_fuel_cv": float(daily.std() / daily.mean()) if daily.mean() > 0 else 0.0}
