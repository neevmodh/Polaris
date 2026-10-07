"""Spend-based Scope 3 using EPA USEEIO v1.3 supply-chain factors (with margins)."""
from pathlib import Path
import numpy as np, pandas as pd
from carbon import factors as F

USEEIO_CSV = Path(__file__).resolve().parents[1] / "data" / "raw" / "useeio_v1.3.csv"

# category key -> (2017 NAICS code, label, GHG Protocol Scope 3 category)
CATEGORIES = {
    "steel":        (331110, "Iron & steel", "Cat 1 Purchased goods"),
    "cement":       (327310, "Cement", "Cat 1 Purchased goods"),
    "plastics":     (325211, "Plastic resins", "Cat 1 Purchased goods"),
    "packaging":    (326112, "Plastic packaging", "Cat 1 Purchased goods"),
    "textiles":     (313310, "Textiles", "Cat 1 Purchased goods"),
    "electronics":  (334111, "Computers & electronics", "Cat 2 Capital goods"),
    "office":       (339940, "Office supplies", "Cat 1 Purchased goods"),
    "it_services":  (541512, "IT services", "Cat 1 Purchased services"),
    "consulting":   (541611, "Management consulting", "Cat 1 Purchased services"),
    "freight":      (484121, "Road freight", "Cat 4 Upstream transport"),
    "courier":      (492110, "Courier / express", "Cat 4 Upstream transport"),
    "waste":        (562111, "Waste collection", "Cat 5 Waste"),
    "air_travel":   (481219, "Air travel", "Cat 6 Business travel"),
    "hotels":       (721110, "Hotels", "Cat 6 Business travel"),
}
_EF_COL = "Supply Chain Emission Factors with Margins"


def load_useeio(path=USEEIO_CSV) -> pd.Series:
    df = pd.read_csv(path)
    return df.set_index("2017 NAICS Code")[_EF_COL]


def ef_kg_per_inr(key: str, table: pd.Series | None = None) -> float:
    table = load_useeio() if table is None else table
    return float(table.loc[CATEGORIES[key][0]]) / F.USD_TO_INR


def _check(spend_inr: dict):
    bad = set(spend_inr) - set(CATEGORIES)
    if bad: raise KeyError(f"unknown Scope 3 categories {sorted(bad)}; valid: {sorted(CATEGORIES)}")
    for k, v in spend_inr.items():
        if not np.isfinite(v) or v < 0: raise ValueError(f"spend for {k!r} must be a finite number >= 0, got {v!r}")


def scope3(spend_inr: dict) -> float:
    """spend_inr {'steel': 5e7, ...} (INR) -> tonnes CO2e."""
    _check(spend_inr)
    t = load_useeio()
    return sum(amt * ef_kg_per_inr(k, t) for k, amt in spend_inr.items()) / 1000


def breakdown(spend_inr: dict) -> pd.DataFrame:
    t = load_useeio()
    rows = [{"category": CATEGORIES[k][1], "ghg_protocol": CATEGORIES[k][2], "spend_inr": a,
             "tco2e": a * ef_kg_per_inr(k, t) / 1000} for k, a in spend_inr.items() if a > 0]
    return pd.DataFrame(rows).sort_values("tco2e", ascending=False)


def monte_carlo_terms(spend_inr: dict, rng: np.random.Generator, n: int) -> dict:
    """tCO2e samples per category (independent lognormal factor error). Draw order is stable, so seeded totals are unchanged."""
    t, s = load_useeio(), F.SPEND_EF_SIGMA
    return {k: amt * ef_kg_per_inr(k, t) * np.exp(rng.normal(-s * s / 2, s, n)) / 1000 for k, amt in spend_inr.items()}


def monte_carlo(spend_inr: dict, rng: np.random.Generator, n: int) -> np.ndarray:
    terms = monte_carlo_terms(spend_inr, rng, n)
    return sum(terms.values()) if terms else np.zeros(n)
