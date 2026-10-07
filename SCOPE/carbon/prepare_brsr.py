"""Adapter: real BRSR Principle-6 file (dataful.in) -> same schema as data_synth.
UNTESTED against the real file (not available when written). Run `python -m carbon.explore <csv>` first
and adjust classify() / unit handling to match the actual wording.
Usage: python -m carbon.prepare_brsr data/raw/brsr_ghg.csv"""
import sys, numpy as np, pandas as pd


def classify(t: str):
    t = str(t).lower()
    inten = any(w in t for w in ("intensity", "per rupee", "turnover"))
    if inten and "scope 1" in t and "scope 2" in t:      # BRSR reports ONE combined S1+S2 intensity
        return "int_s12"
    for n in ("1", "2", "3"):
        if f"scope {n}" in t and not (n == "1" and "scope 2" in t):
            return f"int_s{n}" if inten else f"s{n}"
    return None


def main(path):
    df = pd.read_csv(path)
    df["col"] = df["type_of_emissions"].map(classify)
    df = df.dropna(subset=["col"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["year"] = pd.to_datetime(df["end_date"], errors="coerce").dt.year
    df = df.dropna(subset=["value", "year"])
    w = df.pivot_table(index=["company_name", "sector", "main_business_activity", "year"],
                       columns="col", values="value", aggfunc="first").reset_index()
    # turnover = (S1 + S2) / combined intensity. Intensity is per rupee unless the unit text says crore.
    per_crore = df[df["col"] == "int_s12"]["unit"].astype(str).str.lower().str.contains("crore").mean() > 0.5
    scale = 1.0 if per_crore else 1e7                      # rupees -> crore
    w["turnover_cr"] = np.nan
    if "int_s12" in w:
        m = (w["s1"] > 0) & (w["s2"] > 0) & (w["int_s12"] > 0)
        w.loc[m, "turnover_cr"] = (w.loc[m, "s1"] + w.loc[m, "s2"]) / w.loc[m, "int_s12"] / scale
    print("intensity unit assumed:", "per crore" if per_crore else "per rupee", "| turnover_cr median:", w["turnover_cr"].median())
    w = w.rename(columns={"main_business_activity": "activity"})
    w["employees"], w["renewable_share"] = np.nan, np.nan
    w = w[(w.turnover_cr > 0) & (w.s1 > 0) & (w.s2 > 0)]
    w[["company_name", "sector", "activity", "year", "turnover_cr", "employees", "renewable_share", "s1", "s2"]] \
        .to_parquet("data/processed/company_year.parquet", index=False)
    open("data/processed/DATA_SOURCE.txt", "w").write("BRSR")
    print("saved", w.shape, "[BRSR]")


if __name__ == "__main__":
    main(sys.argv[1])
