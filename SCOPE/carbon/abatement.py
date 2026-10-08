"""Abatement levers, Marginal Abatement Cost Curve (MACC) and Monte-Carlo pathway to 2050.
All costs/efficacies are ILLUSTRATIVE ASSUMPTIONS exposed as parameters, not measured results."""
from dataclasses import dataclass
import numpy as np, pandas as pd
from carbon import factors as F


@dataclass
class Lever:
    name: str
    scope: int
    abatement_t: float          # tCO2e per year at full adoption (today's grid factor)
    cost_inr_per_t: float       # negative = saves money
    grid_linked: bool = False   # abatement shrinks as the grid decarbonises
    eligible_t: float | None = None  # activity boundary, before performance uncertainty


def build_levers(diesel_l, kwh, s3_total_t, diesel_saved_frac=0.268, fuel_price=80.0,
                 solar_kwh=0.0, solar_lcoe=3.5, grid_tariff=8.0, ppa_share=0.0, ppa_premium=0.5,
                 supplier_cut=0.10, supplier_cost_per_t=1500.0, td_loss=0.0) -> list[Lever]:
    for nm, v in (("diesel_saved_frac", diesel_saved_frac), ("ppa_share", ppa_share), ("supplier_cut", supplier_cut)):
        if not 0 <= v <= 1: raise ValueError(f"{nm} must be between 0 and 1, got {v}")
    for nm, v in (("diesel_l", diesel_l), ("kwh", kwh), ("s3_total_t", s3_total_t), ("solar_kwh", solar_kwh)):
        if not np.isfinite(v) or v < 0: raise ValueError(f"{nm} must be a finite number >= 0, got {v}")
    if not np.isfinite(td_loss) or not 0 <= td_loss < 1:
        raise ValueError("td_loss must be between 0 (inclusive) and 1 (exclusive)")
    g = F.GRID_EF_KG_PER_KWH / (1 - td_loss)
    L = []
    if diesel_l and diesel_saved_frac:
        L.append(Lever("Polaris dispatch optimisation", 1, diesel_l * diesel_saved_frac * F.FUEL_EF["diesel_l"] / 1000,
                       -fuel_price / F.FUEL_EF["diesel_l"] * 1000, eligible_t=diesel_l * F.FUEL_EF["diesel_l"] / 1000))
    solar_used = min(solar_kwh, kwh)                      # self-consumed solar cannot offset more than the grid draw
    if solar_used:
        L.append(Lever("On-site solar", 2, solar_used * g / 1000, (solar_lcoe - grid_tariff) / g * 1000, True, solar_used * g / 1000))
    ppa_kwh = (kwh - solar_used) * ppa_share              # PPA applies only to grid kWh left after solar (no double count)
    if ppa_kwh:
        L.append(Lever("Green open-access PPA", 2, ppa_kwh * g / 1000, ppa_premium / g * 1000, True, ppa_kwh * g / 1000))
    if supplier_cut:
        L.append(Lever("Supplier engagement (Scope 3)", 3, s3_total_t * supplier_cut, supplier_cost_per_t, eligible_t=s3_total_t))
    return L


def macc(levers) -> pd.DataFrame:
    if not levers:
        return pd.DataFrame(columns=["name", "scope", "abatement_t", "cost_inr_per_t", "grid_linked", "cumulative_t", "annual_net_cost_inr"])
    d = pd.DataFrame([l.__dict__ for l in levers]).sort_values("cost_inr_per_t").reset_index(drop=True)
    d["cumulative_t"] = d["abatement_t"].cumsum()
    d["annual_net_cost_inr"] = d["abatement_t"] * d["cost_inr_per_t"]
    return d


def pathway(s1, s2, s3, levers, start=2026, end=2050, adoption_years=4, n=2000, seed=42, sbti_rate=0.042) -> pd.DataFrame:
    """P10/P50/P90 total footprint: business-as-usual vs with levers; plus an SBTi 1.5C-aligned line."""
    if adoption_years < 1 or end < start: raise ValueError("adoption_years must be >= 1 and end >= start")
    if any(not np.isfinite(v) or v < 0 for v in (s1, s2, s3)):
        raise ValueError("Scope baselines must be finite and nonnegative")
    if any(l.scope not in (1, 2, 3) or l.abatement_t < 0 for l in levers):
        raise ValueError("Levers must target Scope 1, 2 or 3 with nonnegative abatement")
    rng = np.random.default_rng(seed)
    decl = rng.triangular(0.01, F.GRID_DECLINE_PER_YEAR, 0.04, n)          # grid decarbonisation uncertainty
    eff = rng.triangular(0.7, 1.0, 1.15, (n, len(levers))) if levers else np.zeros((n, 0))
    rows = []
    for i, yr in enumerate(range(start, end + 1)):
        ramp = min((i + 1) / adoption_years, 1.0)
        gf = (1 - decl) ** i
        bau = s1 + s2 * gf + s3
        reductions = {scope: np.zeros(n) for scope in (1, 2, 3)}
        for j, l in enumerate(levers):
            cut = l.abatement_t * eff[:, j] * ramp
            if l.eligible_t is not None:
                cut = np.minimum(cut, l.eligible_t)
            reductions[l.scope] += cut * (gf if l.grid_linked else 1.0)
        pol = (np.maximum(s1 - reductions[1], 0)
               + np.maximum(s2 * gf - reductions[2], 0)
               + np.maximum(s3 - reductions[3], 0))
        q = lambda a: np.percentile(a, [10, 50, 90])
        b10, b50, b90 = q(bau); p10, p50, p90 = q(pol)
        rows.append({"year": yr, "bau_p10": b10, "bau_p50": b50, "bau_p90": b90,
                     "with_levers_p10": p10, "with_levers_p50": p50, "with_levers_p90": p90,
                     "sbti_1p5C_line": max((s1 + s2 + s3) * (1 - sbti_rate * (i + 1)), 0)})
    return pd.DataFrame(rows)


def cumulative_abated(path: pd.DataFrame, upto=2030) -> float:
    p = path[path.year <= upto]
    return float((p.bau_p50 - p.with_levers_p50).sum())
