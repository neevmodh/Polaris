"""One planning window as a mixed-integer linear program (HiGHS through scipy.optimize.milp).
Hourly energy balance, generator on/off with a minimum load and a no-load fuel term, battery with efficiencies (simultaneous charge and
discharge is never optimal because both cost wear and round-trip loss; a test asserts it never happens), flexible load that may move inside blocks, unmet-demand slack that is always visible, and a fuel inventory limit."""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
from carbon.microgrid import Profile

CO2_KG_PER_L = 2.70
BIG = 1e4                                  # price of one unserved kWh (INR-like units): the plan avoids it unless physically unavoidable
MODES = ("economy", "green", "survival")


@dataclass
class Plan:
    status: str
    g: np.ndarray; u: np.ndarray; pv_used: np.ndarray; wind_used: np.ndarray; charge: np.ndarray; discharge: np.ndarray
    soc: np.ndarray; flex: np.ndarray; unmet: np.ndarray; flex_curtailed_kwh: float; fuel_l: np.ndarray; objective: float
    shed: np.ndarray = None; budget_overshoot_l: float = 0.0


class _Model:
    def __init__(self):
        self.lb, self.ub, self.integ, self.cost = [], [], [], []
        self.rows, self.cols, self.vals, self.rlo, self.rhi = [], [], [], [], []

    def var(self, lb=0.0, ub=np.inf, integer=False, cost=0.0) -> int:
        self.lb.append(lb); self.ub.append(ub); self.integ.append(1 if integer else 0); self.cost.append(cost)
        return len(self.lb) - 1

    def con(self, coeffs: dict, lo=-np.inf, hi=np.inf):
        r = len(self.rlo)
        for j, v in coeffs.items():
            self.rows.append(r); self.cols.append(j); self.vals.append(v)
        self.rlo.append(lo); self.rhi.append(hi)

    def solve(self, time_limit, gap):
        A = coo_matrix((self.vals, (self.rows, self.cols)), shape=(len(self.rlo), len(self.lb))).tocsr()
        res = milp(c=np.array(self.cost), constraints=LinearConstraint(A, self.rlo, self.rhi), integrality=np.array(self.integ),
                   bounds=Bounds(self.lb, self.ub), options={"time_limit": time_limit, "mip_rel_gap": gap, "presolve": True})
        return res


def solve_window(p: Profile, essential, normal, flex_base, pv, wind, soc0_kwh, mode="economy", fuel_stock_l=None, fuel_budget_l=None,
                 prev_on=0, soc_end_frac=None, flex_curtail_frac=0.0, time_limit=5.0, gap=0.03) -> Plan:
    """Plan the next len(pv) hours. Three load classes: `essential` (always served), `normal` (served unless Survival rations it) and
    `flex_base` (may move inside its block, and be curtailed in Survival). With a fuel budget (Survival) the budget is a hard limit, so
    rationing of non-essential load, never silent blackouts of essential load, absorbs any shortage."""
    if mode not in MODES: raise ValueError(f"mode must be one of {MODES}")
    H = len(pv); Gmax, Gmin, Pb, E = p.gen_kw, p.gen_min_kw, p.battery_kw, p.battery_kwh
    m = _Model(); fuel_unit = p.fuel_price
    if mode == "economy":   w_fuel, w_start, w_wear = p.fuel_price, p.start_cost, p.battery_wear
    elif mode == "green":   w_fuel, w_start, w_wear = CO2_KG_PER_L, p.start_cost / p.fuel_price * CO2_KG_PER_L * 0.25, p.battery_wear / p.fuel_price * CO2_KG_PER_L * 0.05
    else:                   w_fuel, w_start, w_wear = p.fuel_price * 1.0, p.start_cost, p.battery_wear
    unmet_c = BIG * (p.fuel_price / 80.0) if mode != "green" else BIG * CO2_KG_PER_L / 80.0 * 20
    curt_c = 1e-3 * w_fuel
    flex_cap = 2.0 * float(np.max(flex_base)) + 1e-6 if len(flex_base) else 0.0
    g, u, s, pvu, wu, c, d, f, un, sh = ([] for _ in range(10))
    shed_c = 300.0 * p.fuel_price / 80.0 if mode == "survival" else 0.9 * unmet_c
    for t in range(H):
        g.append(m.var(0, Gmax, cost=w_fuel * p.fuel_a)); u.append(m.var(0, 1, True, cost=w_fuel * p.fuel_b * Gmax)); s.append(m.var(0, 1, cost=w_start))
        pvu.append(m.var(0, max(float(pv[t]), 0.0), cost=-curt_c)); wu.append(m.var(0, max(float(wind[t]), 0.0), cost=-curt_c))
        c.append(m.var(0, Pb, cost=w_wear)); d.append(m.var(0, Pb, cost=w_wear))
        f.append(m.var(0, flex_cap)); un.append(m.var(0, np.inf, cost=unmet_c)); sh.append(m.var(0, max(float(normal[t]), 0.0), cost=shed_c))
    socv = [m.var(p.soc_min * E, p.soc_max * E) for _ in range(H)]
    for t in range(H):
        rhs = float(essential[t] + normal[t])
        m.con({g[t]: 1, pvu[t]: 1, wu[t]: 1, d[t]: 1, c[t]: -1, un[t]: 1, sh[t]: 1, f[t]: -1}, rhs, rhs)
        m.con({g[t]: 1, u[t]: -Gmax}, hi=0); m.con({g[t]: 1, u[t]: -Gmin}, lo=0)
        m.con({s[t]: 1, u[t]: -1, **({u[t - 1]: 1} if t else {})}, lo=-(prev_on if t == 0 else 0))
        row = {socv[t]: 1, c[t]: -p.eta_c, d[t]: 1 / p.eta_d}
        if t: row[socv[t - 1]] = -1
        m.con(row, soc0_kwh if t == 0 else 0, soc0_kwh if t == 0 else 0)
    if soc_end_frac is not None: m.con({socv[H - 1]: 1}, lo=min(soc_end_frac * E, p.soc_max * E))
    # flexible load: energy inside each block is conserved (or curtailed up to a stated share)
    W = p.flex_window_h; fc_total = []
    for b0 in range(0, H, W):
        blk = list(range(b0, min(b0 + W, H))); tot = float(np.sum(np.asarray(flex_base)[blk]))
        fc = m.var(0, flex_curtail_frac * tot, cost=(100.0 if mode == "survival" else 60.0) * p.fuel_price / 80.0); fc_total.append(fc)
        m.con({**{f[t]: 1 for t in blk}, fc: 1}, tot, tot)
    fuel_expr = {**{g[t]: p.fuel_a for t in range(H)}, **{u[t]: p.fuel_b * Gmax for t in range(H)}}
    if fuel_stock_l is not None: m.con(fuel_expr, hi=max(fuel_stock_l, 0.0))
    if fuel_budget_l is not None:
        m.con(fuel_expr, hi=max(fuel_budget_l, 0.0))                          # hard pace limit toward the resupply date; shedding makes it always feasible
    res = m.solve(time_limit, gap)
    if res.x is None:
        raise RuntimeError(f"planning window could not be solved: {res.message}")
    x = res.x; arr = lambda ids: np.array([x[i] for i in ids])
    gg, uu = arr(g), np.round(arr(u))
    return Plan(status=res.message, g=gg, u=uu, pv_used=arr(pvu), wind_used=arr(wu), charge=arr(c), discharge=arr(d), soc=arr(socv), flex=arr(f),
                unmet=arr(un), flex_curtailed_kwh=float(sum(x[i] for i in fc_total)), fuel_l=p.fuel_a * gg + p.fuel_b * Gmax * uu,
                objective=float(res.fun), shed=arr(sh))
