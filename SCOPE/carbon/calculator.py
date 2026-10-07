from dataclasses import dataclass
import numpy as np
from carbon import factors as F, scope3 as S3


@dataclass
class Footprint:
    scope1_t: float
    scope2_t: float
    scope3_t: float

    @property
    def total_t(self) -> float:
        return self.scope1_t + self.scope2_t + self.scope3_t


def _nonneg(x, name):
    """Reject negative, NaN or infinite activity data instead of silently producing nonsense."""
    if not isinstance(x, (int, float, np.integer, np.floating)) or not np.isfinite(x) or x < 0:
        raise ValueError(f"{name} must be a finite number >= 0, got {x!r}")
    return float(x)


def scope1(fuel_use: dict) -> float:
    """fuel_use: {'diesel_l': 84000, ...} -> tonnes CO2 (CO2 only; CH4/N2O from combustion are small and excluded)"""
    bad = set(fuel_use) - set(F.FUEL_EF)
    if bad: raise KeyError(f"unknown fuel(s) {sorted(bad)}; valid: {sorted(F.FUEL_EF)}")
    return sum(_nonneg(q, k) * F.FUEL_EF[k] for k, q in fuel_use.items()) / 1000


def scope2(kwh: float, ef_kg_per_kwh: float = F.GRID_EF_KG_PER_KWH, td_loss: float = 0.0) -> float:
    """Location-based Scope 2. CEA factors are generation-side; set td_loss (e.g. 0.17) to gross up for
    transmission & distribution losses. Default 0 matches the published CEA figure. Market-based Scope 2 not covered."""
    if not 0 <= td_loss < 1: raise ValueError("td_loss must be in [0, 1)")
    return _nonneg(kwh, "kWh") / (1 - td_loss) * ef_kg_per_kwh / 1000


def footprint(fuel_use: dict, kwh: float, spend_inr: dict, td_loss: float = 0.0) -> Footprint:
    return Footprint(scope1(fuel_use), scope2(kwh, td_loss=td_loss), S3.scope3(spend_inr))


FUEL_LABEL = {"diesel_l": "Diesel", "petrol_l": "Petrol", "lpg_kg": "LPG", "natural_gas_m3": "Natural gas"}


def drivers(fuel_use, kwh, spend_inr, n=5000, seed=42, td_loss=0.0, top=8) -> list:
    """Which emission factor contributes how much of the uncertainty in the total.
    The terms are independent, so each term's share of the total variance is exact: var(term) / var(total)."""
    scope1(fuel_use); scope2(kwh, td_loss=td_loss); S3.scope3(spend_inr)
    rng = np.random.default_rng(seed)
    ln = lambda m, s: m * np.exp(rng.normal(-s * s / 2, s, n))
    terms = {f"{FUEL_LABEL[k]} factor": (1, q * ln(F.FUEL_EF[k], F.FUEL_EF_SIGMA) / 1000) for k, q in fuel_use.items() if q}
    if kwh: terms["Grid emission factor"] = (2, kwh / (1 - td_loss) * ln(F.GRID_EF_KG_PER_KWH, F.GRID_EF_SIGMA) / 1000)
    for k, a in S3.monte_carlo_terms({k: v for k, v in spend_inr.items() if v}, rng, n).items():
        terms[f"{S3.CATEGORIES[k][1]} factor"] = (3, a)
    if not terms: return []
    var_total = float(np.var(sum(a for _, a in terms.values())))
    if var_total <= 0: return []
    rows = [{"name": k, "scope": sc, "share": float(np.var(a)) / var_total, "tco2e_sd": float(np.std(a))} for k, (sc, a) in terms.items()]
    rows.sort(key=lambda r: -r["share"])
    return rows[:top]


def monte_carlo(fuel_use, kwh, spend_inr, n=5000, seed=42, td_loss=0.0) -> dict:
    """Propagate emission-factor uncertainty (lognormal) -> P5/P50/P95 per scope and total."""
    scope1(fuel_use); scope2(kwh, td_loss=td_loss); S3.scope3(spend_inr)      # validate inputs once
    rng = np.random.default_rng(seed)
    ln = lambda m, s: m * np.exp(rng.normal(-s * s / 2, s, n))
    s1 = sum(q * ln(F.FUEL_EF[k], F.FUEL_EF_SIGMA) for k, q in fuel_use.items()) / 1000
    s2 = kwh / (1 - td_loss) * ln(F.GRID_EF_KG_PER_KWH, F.GRID_EF_SIGMA) / 1000
    s3 = S3.monte_carlo(spend_inr, rng, n)
    out = {}
    for name, a in (("scope1", s1), ("scope2", s2), ("scope3", s3), ("total", s1 + s2 + s3)):
        p5, p50, p95 = np.percentile(a, [5, 50, 95])
        out[name] = {"p5": float(p5), "p50": float(p50), "p95": float(p95)}
    return out
