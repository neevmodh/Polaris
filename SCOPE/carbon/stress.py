"""Hard stress tests on the SHIPPED models. Writes results/stress.json (shown in the web Model report).
Each test says what it checks, the number, and whether it passed. Failures of the 'limits' group are expected and are reported honestly."""
import json, warnings
import joblib, numpy as np, pandas as pd
from sklearn.base import clone
from sklearn.metrics import mean_squared_error
from carbon import data_synth, train as T

warnings.filterwarnings("ignore")
rmse = lambda y, p: float(np.sqrt(mean_squared_error(y, p)))


def load(tgt): return joblib.load(f"models/model_{tgt}.joblib")


def score(tgt, df, b=None):
    b = b or load(tgt); X = df[b["features"]]; y = np.log1p(df[tgt].values)
    p = b["pipeline"].predict(X); hw = T.hw_of(b["conformal"], X, df["sector"].values)
    return y, p, hw, np.abs(y - p) <= hw


def main(n_fresh=3000):
    base = T.add_features(pd.read_parquet("data/processed/company_year.parquet"))
    train, _, _ = T.split(base)
    fresh = T.add_features(data_synth.generate(n_fresh, seed=2026))          # a world the models never saw
    out, rows = {"n_fresh_companies": n_fresh, "tests": []}, []
    add = lambda group, name, value, passed, detail: rows.append(dict(group=group, name=name, value=value, passed=passed, detail=detail))

    for tgt in ("s1", "s2"):
        b = load(tgt); y, p, hw, cov = score(tgt, fresh, b); X = fresh[b["features"]]
        bl = T.SectorMedianBaseline().fit(train[b["features"]], np.log1p(train[tgt].values)).predict(X)
        add("accuracy", f"{tgt.upper()} error vs sector-median baseline", rmse(y, p) / rmse(y, bl), rmse(y, p) / rmse(y, bl) < 0.75,
            f"RMSE {rmse(y, p):.3f} vs {rmse(y, bl):.3f} on {len(fresh)} unseen company-years; pass if ratio < 0.75")
        add("calibration", f"{tgt.upper()} 90% interval coverage", float(cov.mean()), 0.87 <= cov.mean() <= 0.94, "pass if within 87–94%")
        sec = pd.Series(cov).groupby(fresh["sector"].values).mean()
        add("calibration", f"{tgt.upper()} worst-sector coverage", float(sec.min()), sec.min() >= 0.80, f"{sec.idxmin()} (pass if ≥ 80%)")
        terc = pd.qcut(fresh["log_turnover"], 3, labels=["small", "mid", "large"]); tc = pd.Series(cov).groupby(terc.values).mean()
        add("calibration", f"{tgt.upper()} coverage across company size", float(tc.min()), tc.min() >= 0.82, "small/mid/large: " + ", ".join(f"{k} {v:.0%}" for k, v in tc.items()))
        yc = pd.Series(cov).groupby(fresh["year"].values).mean()
        add("calibration", f"{tgt.upper()} coverage across years", float(yc.min()), yc.min() >= 0.82, f"worst year {yc.idxmin()} at {yc.min():.0%}")

        # perturbation: ±10% turnover should move the estimate by about the elasticity, never wildly
        d = fresh.sample(1500, random_state=1).copy(); p0 = b["pipeline"].predict(d[b["features"]]); mx = 0
        for f in (0.9, 1.1):
            e = d.copy(); e["log_turnover"] = e["log_turnover"] + np.log10(f); mx = max(mx, float(np.median(np.abs(b["pipeline"].predict(e[b["features"]]) - p0))))
        add("robustness", f"{tgt.upper()} ±10% turnover moves estimate (median, log units)", mx, mx < 0.15, "elasticity ≈ 0.9 ⇒ expect ≈ 0.09")
        # missing optional inputs
        if "log_employees" in b["features"] or "renewable_share" in b["features"]:
            m = fresh.copy()
            for c in ("log_employees", "renewable_share"):
                if c in m: m[c] = np.nan
            y2, p2, _, _ = score(tgt, m, b)
            add("robustness", f"{tgt.upper()} error when employees and renewable share are missing", rmse(y2, p2) / rmse(y, p), rmse(y2, p2) / rmse(y, p) < 1.25, f"RMSE {rmse(y2, p2):.3f} vs {rmse(y, p):.3f}; pass if < 25% worse")
        # row order must not matter
        sh = fresh.sample(frac=1, random_state=3); ys, ps, _, _ = score(tgt, sh, b)
        add("robustness", f"{tgt.upper()} prediction independent of row order", abs(rmse(ys, ps) - rmse(y, p)), abs(rmse(ys, ps) - rmse(y, p)) < 1e-9, "same data shuffled")
        # learning curve: is more data still helping, or are we saturated / overfit?
        te = fresh.sample(1500, random_state=9); lc = []
        for frac in (0.1, 0.25, 0.5, 1.0):
            sub = train.sample(frac=frac, random_state=4); m = clone(b["pipeline"]).fit(sub[b["features"]], np.log1p(sub[tgt].values))
            lc.append(rmse(np.log1p(te[tgt].values), m.predict(te[b["features"]])))
        add("robustness", f"{tgt.upper()} learning curve flattens (10% → 100% of training data)", lc[-1] / lc[-2], lc[-2] / lc[-1] < 1.05 and lc[-1] <= lc[0],
            "test RMSE " + " → ".join(f"{v:.3f}" for v in lc) + "; pass if the last doubling gains < 5%")
        out.setdefault("learning_curve", {})[tgt] = {"fractions": [0.1, 0.25, 0.5, 1.0], "rmse": lc}

        # LIMITS: situations the model is not built for. These are expected to degrade; we report how much.
        sh1 = fresh.copy(); sh1[tgt] = sh1[tgt] * 1.5; _, _, _, c1 = score(tgt, sh1, b)
        add("limits", f"{tgt.upper()} regime shift: every company's true emissions +50%", float(c1.mean()), None, "intervals stop covering; the model cannot see a shift it was not trained on")
        sh2 = fresh.copy(); m_ = sh2["sector"] == "Cement"; sh2.loc[m_, tgt] = sh2.loc[m_, tgt] * 2; _, _, _, c2 = score(tgt, sh2, b)
        add("limits", f"{tgt.upper()} one sector doubles (cement): coverage in that sector", float(c2[m_.values].mean()), None, f"other sectors stay at {c2[~m_.values].mean():.0%}")
        ol = fresh.copy(); idx = ol.sample(frac=0.01, random_state=5).index; ol.loc[idx, tgt] = ol.loc[idx, tgt] * 1000   # unit-entry errors
        _, _, _, c3 = score(tgt, ol, b)
        add("limits", f"{tgt.upper()} 1% of labels wrong by ×1000 (unit errors)", float(c3.mean()), None, "BRSR is known to contain such entries: clean before training")
    out["tests"] = rows
    gated = [r for r in rows if r["passed"] is not None]
    out["passed"], out["total"] = sum(bool(r["passed"]) for r in gated), len(gated)
    json.dump(out, open("results/stress.json", "w"), indent=2, default=float)
    for r in rows:
        mark = "  --" if r["passed"] is None else ("PASS" if r["passed"] else "FAIL")
        print(f"{mark} [{r['group']:11s}] {r['name']}: {r['value']:.3f}  ({r['detail']})")
    print(f"\n{out['passed']}/{out['total']} gated stress tests passed")
    return out


if __name__ == "__main__":
    main()
