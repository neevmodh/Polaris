import joblib, numpy as np, pandas as pd
from functools import lru_cache
from carbon.train import hw_of


@lru_cache(maxsize=4)
def _load(tgt, models_dir="models"): return joblib.load(f"{models_dir}/model_{tgt}.joblib")


def data_source() -> str: return _load("s1")["data_source"]


def predict(sector, activity, turnover_cr, employees=None, renewable_share=0.1, year=2026, models_dir="models") -> dict:
    """tCO2e point estimate + 90% conformal interval for Scope 1 and 2, plus out-of-distribution warnings."""
    if not (np.isfinite(turnover_cr) and turnover_cr > 0): raise ValueError(f"turnover_cr must be a finite number > 0, got {turnover_cr!r}")
    if employees is not None and not (np.isfinite(employees) and employees > 0): raise ValueError("employees must be > 0 or None")
    if not 0 <= renewable_share <= 1: raise ValueError("renewable_share must be between 0 and 1")
    if not np.isfinite(year): raise ValueError("year must be finite")
    row = pd.DataFrame([{"sector": sector, "activity": activity, "log_turnover": np.log10(turnover_cr),
                         "log_employees": np.log10(employees) if employees else np.nan,
                         "year": year, "renewable_share": renewable_share}])
    out = {"warnings": []}
    for t in ("s1", "s2"):
        b = _load(t, models_dir); X = row[b["features"]]
        p = float(b["pipeline"].predict(X)[0]); hw = float(hw_of(b["conformal"], X, [sector])[0])
        out[t] = {"point": float(np.expm1(p)), "lo": float(np.expm1(p - hw)), "hi": float(np.expm1(p + hw)), "model": b["model"]}
    b = _load("s1", models_dir)
    if sector not in b["sectors"]: out["warnings"].append(f"Sector '{sector}' unseen in training: estimate unreliable.")
    if activity not in b["activities"]: out["warnings"].append(f"Activity '{activity}' unseen in training.")
    lo, hi = b["train_range"]["log_turnover"]
    if not lo <= np.log10(turnover_cr) <= hi: out["warnings"].append("Turnover outside the training range: extrapolation, widen your tolerance.")
    ylo, yhi = b["train_range"]["year"]
    if year > yhi + 1 or year < ylo: out["warnings"].append(f"Year {year} is outside the training data ({ylo}-{yhi}); no trend extrapolation is reliable.")
    return out


if __name__ == "__main__":
    df = pd.read_parquet("data/processed/company_year.parquet")
    rows = []
    for _, r in df.sample(8, random_state=7).iterrows():
        p = predict(r.sector, r.activity, r.turnover_cr, r.employees if r.employees == r.employees else None, r.renewable_share, int(r.year))
        rows.append({"company": r.company_name, "sector": r.sector, "year": int(r.year),
                     "actual_s1": r.s1, "pred_s1": p["s1"]["point"], "s1_lo": p["s1"]["lo"], "s1_hi": p["s1"]["hi"],
                     "actual_s2": r.s2, "pred_s2": p["s2"]["point"], "s2_lo": p["s2"]["lo"], "s2_hi": p["s2"]["hi"]})
    out = pd.DataFrame(rows).round(1); out["data_source"] = data_source()
    out.to_csv("outputs/sample_inference.csv", index=False); print(out.to_string())
    print("\nNOTE: rows may be in the training set; honest accuracy is results/metrics.json (held-out companies).")
