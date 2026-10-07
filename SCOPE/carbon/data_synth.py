"""SYNTHETIC company-year emissions data, used ONLY until the real BRSR file is available.
Intensities are illustrative assumptions (tCO2e per INR crore of turnover), NOT measured values.
Every artefact trained on this data is stamped data_source = "SYNTHETIC"."""
import numpy as np, pandas as pd

# sector: (scope1 intensity, scope2 intensity, company-effect sigma)
SECTORS = {
    "Cement": (900, 60, .35), "Iron & Steel": (1200, 80, .40), "Power Generation": (3000, 10, .50),
    "Oil & Gas": (1500, 40, .60), "Chemicals": (250, 70, .50), "Textiles": (80, 50, .45),
    "Pharmaceuticals": (40, 35, .45), "FMCG": (25, 15, .50), "Automobiles": (30, 20, .50),
    "Real Estate & Construction": (60, 10, .55), "IT Services": (3, 8, .50), "Banking & Finance": (1, 3, .50),
}
ACTIVITY_MULT = [0.6, 1.0, 1.6]
DECLINE = {k: v for k, v in zip(SECTORS, [.01, .02, .005, .015, .03, .04, .035, .03, .03, .02, .05, .05])}   # per-sector yearly intensity decline


def generate(n_companies=1500, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    names = list(SECTORS)
    rows = []
    for i in range(n_companies):
        sec = names[rng.integers(len(names))]
        i1, i2, sg = SECTORS[sec]
        k = rng.integers(3)
        t0 = np.exp(rng.normal(np.log(2000), 1.4))                 # INR crore, 2020
        emp = np.exp(rng.normal(np.log(5 * t0 ** 0.75), 0.5))
        u1, u2, ren0 = rng.normal(0, sg), rng.normal(0, sg), rng.beta(2, 6)
        decl = DECLINE[sec]
        for year in range(2020, 2026):
            if rng.random() > 0.85:
                continue
            turn = t0 * 1.08 ** (year - 2020)
            ren = min(ren0 + 0.03 * (year - 2020) + rng.normal(0, .02), .95)
            size_eff = (turn / 2000) ** -0.06                                  # economies of scale (non-linear in size)
            green = 1 - 0.7 * np.clip((ren - 0.3) / 0.4, 0, 1) if sec == "Power Generation" else 1.0   # interaction
            s1 = i1 * ACTIVITY_MULT[k] * turn * size_eff * green * np.exp(u1 - decl * (year - 2020) + 0.12 * rng.standard_t(5))
            s2 = i2 * turn * size_eff * np.exp(u2 + 0.12 * rng.standard_t(5)) * (1 - 0.6 * ren)
            rows.append({"company_name": f"SynthCo {i:04d}", "sector": sec, "activity": f"{sec} / type {k}",
                         "year": year, "turnover_cr": turn,
                         "employees": np.nan if rng.random() < .2 else emp,
                         "renewable_share": ren, "s1": s1, "s2": s2})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = generate()
    df.attrs["data_source"] = "SYNTHETIC"
    df.to_parquet("data/processed/company_year.parquet", index=False)
    open("data/processed/DATA_SOURCE.txt", "w").write("SYNTHETIC")
    print(df.shape, "companies:", df.company_name.nunique(), "-> data/processed/company_year.parquet [SYNTHETIC]")
