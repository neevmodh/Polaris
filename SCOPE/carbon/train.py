"""Model zoo + grouped tuning + overfit audit + adaptive conformal intervals.
Method inspired by Pladifes CGEE (4 models, best by RMSE); code written independently."""
import json, warnings, joblib, numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import randint, uniform, loguniform
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor

warnings.filterwarnings("ignore")
SEED, ALPHA, N_ITER = 42, 0.10, 20
CAT = ["sector", "activity"]
NUM_ALL = ["log_turnover", "log_employees", "year", "renewable_share"]
TARGETS = ("s1", "s2")
SCALE_FLOOR = 0.05


def add_features(df):
    d = df.copy()
    d["log_turnover"] = np.log10(d["turnover_cr"])
    d["log_employees"] = np.log10(d["employees"])
    return d


def usable_numeric(df, min_fill=0.05):
    """Drop numeric features that are (almost) entirely missing or constant (e.g. real BRSR has no employees)."""
    return [c for c in NUM_ALL if df[c].notna().mean() >= min_fill and df[c].nunique() > 1]


def _tree_pre(impute, num):
    return ColumnTransformer([
        ("c", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CAT),
        ("n", SimpleImputer(strategy="median") if impute else "passthrough", num)])


def _lin_pre(num):
    return ColumnTransformer([
        ("c", OneHotEncoder(handle_unknown="ignore"), CAT),
        ("n", Pipeline([("i", SimpleImputer(strategy="median")), ("s", StandardScaler())]), num)])


def zoo(num):
    return {
        "ridge": (Pipeline([("p", _lin_pre(num)), ("m", Ridge())]), {"m__alpha": loguniform(1e-2, 1e2)}),
        "random_forest": (Pipeline([("p", _tree_pre(True, num)), ("m", RandomForestRegressor(n_jobs=-1, random_state=SEED))]),
                          {"m__n_estimators": randint(150, 400), "m__min_samples_leaf": randint(2, 12),
                           "m__max_features": uniform(0.5, 0.5)}),
        "xgboost": (Pipeline([("p", _tree_pre(False, num)), ("m", XGBRegressor(random_state=SEED, n_jobs=-1, tree_method="hist"))]),
                    {"m__n_estimators": randint(100, 400), "m__learning_rate": loguniform(0.02, 0.2),
                     "m__max_depth": randint(2, 6), "m__min_child_weight": randint(3, 20),
                     "m__subsample": uniform(0.6, 0.4), "m__colsample_bytree": uniform(0.6, 0.4),
                     "m__reg_lambda": loguniform(0.5, 20)}),
        "lightgbm": (Pipeline([("p", _tree_pre(False, num)), ("m", LGBMRegressor(random_state=SEED, n_jobs=-1, verbose=-1))]),
                     {"m__n_estimators": randint(100, 400), "m__learning_rate": loguniform(0.02, 0.2),
                      "m__num_leaves": randint(4, 32), "m__min_child_samples": randint(10, 60),
                      "m__subsample": uniform(0.6, 0.4), "m__subsample_freq": [1], "m__colsample_bytree": uniform(0.6, 0.4),
                      "m__reg_lambda": loguniform(0.5, 20)}),
    }


class SectorMedianBaseline:
    """What practitioners use today: sector-median intensity x turnover (log space)."""
    def fit(self, X, y):
        r = pd.Series(y - X["log_turnover"].values, index=X.index)
        self.ratio_, self.glob_ = r.groupby(X["sector"]).median(), float(r.median())
        return self

    def predict(self, X):
        return X["sector"].map(self.ratio_).fillna(self.glob_).values + X["log_turnover"].values


# ---------------------------------------------------------------- conformal
def _q(r, alpha=ALPHA):
    n = len(r); k = int(np.ceil((n + 1) * (1 - alpha)))
    return float(np.sort(r)[min(k, n) - 1])


def conformal_table(abs_res, sectors, min_n=30):
    """Mondrian (per-sector) split-conformal."""
    per = {s: _q(abs_res[sectors == s]) for s in np.unique(sectors) if (sectors == s).sum() >= min_n}
    return {"alpha": ALPHA, "global": _q(abs_res), "per_sector": per}


def half_width(tab, sectors):
    return np.array([tab["per_sector"].get(s, tab["global"]) for s in sectors])


def oof_predictions(pipe, dev, y, num):
    """Out-of-fold predictions, grouped by company: every row is predicted by a model that never saw its company."""
    X = dev[CAT + num]; oof = np.zeros(len(dev))
    for a, b in GroupKFold(5).split(X, y, groups=dev["company_name"]):
        oof[b] = clone(pipe).fit(X.iloc[a], y[a]).predict(X.iloc[b])
    return oof


def _scale_pipe(num):
    return Pipeline([("p", _tree_pre(False, num)),
                     ("m", LGBMRegressor(n_estimators=150, learning_rate=0.05, num_leaves=8, min_child_samples=40,
                                         subsample=.8, subsample_freq=1, random_state=SEED, verbose=-1))])


def fit_scale_model(dev, res, num):
    """|residual| model -> per-row error scale sigma(x). Returns cross-fitted sigma for the scores and a final model for inference."""
    X = dev[CAT + num]; sig = np.zeros(len(dev))
    for a, b in GroupKFold(5).split(X, res, groups=dev["company_name"]):
        sig[b] = _scale_pipe(num).fit(X.iloc[a], res[a]).predict(X.iloc[b])
    return np.maximum(sig, SCALE_FLOOR), _scale_pipe(num).fit(X, res)


def hw_of(conf, X, sectors):
    if conf["method"] == "normalized":
        return conf["q"] * np.maximum(conf["scale_model"].predict(X), SCALE_FLOOR)
    return half_width(conf["mondrian"], sectors)


def interval_score(y, lo, hi, a=ALPHA):
    return float(np.mean((hi - lo) + (2 / a) * (lo - y) * (y < lo) + (2 / a) * (y - hi) * (y > hi)))


def build_conformal(dev, y, pred, num):
    """Cross-conformal: residuals come from out-of-fold predictions over train + calibration companies (about 6x more
    residuals per sector than a single calibration split), which stabilises the per-sector quantiles."""
    res = np.abs(y - pred); sec = dev["sector"].values
    sig, scale = fit_scale_model(dev, res, num)
    # pick the method on one half of the companies, judged on the other half
    comp = dev["company_name"].unique(); rng = np.random.default_rng(SEED); rng.shuffle(comp)
    A = dev["company_name"].isin(comp[: len(comp) // 2]).values; B = ~A
    hwB = {"normalized": _q(res[A] / sig[A]) * sig[B], "mondrian": half_width(conformal_table(res[A], sec[A]), sec[B])}
    sc = {nm: interval_score(y[B], pred[B] - h, pred[B] + h) for nm, h in hwB.items()}
    method = min(sc, key=sc.get)
    final = ({"method": "normalized", "q": _q(res / sig), "scale_model": scale} if method == "normalized"
             else {"method": "mondrian", "mondrian": conformal_table(res, sec)})
    final["selection_interval_scores"] = sc
    return final


# ---------------------------------------------------------------- evaluation
def scores(y, p):
    ape = np.abs(np.expm1(p) - np.expm1(y)) / np.expm1(y)
    return {"rmse_log": float(np.sqrt(mean_squared_error(y, p))), "mae_log": float(mean_absolute_error(y, p)),
            "r2_log": float(r2_score(y, p)), "median_pct_error": float(np.median(ape) * 100)}


def boot_improvement(y, p_model, p_base, groups, n=1000):
    """95% CI (company bootstrap) of RMSE improvement vs baseline, in %."""
    g = pd.Series(range(len(y))).groupby(np.asarray(groups)).apply(list); rng = np.random.default_rng(SEED)
    em, eb = (y - p_model) ** 2, (y - p_base) ** 2; out = []
    for _ in range(n):
        idx = np.concatenate(g.iloc[rng.integers(len(g), size=len(g))].values)
        out.append(1 - np.sqrt(em[idx].mean() / eb[idx].mean()))
    return [float(np.percentile(out, 2.5) * 100), float(np.percentile(out, 97.5) * 100)]


def split(df):
    tr_i, te_i = next(GroupShuffleSplit(1, test_size=.15, random_state=SEED).split(df, groups=df["company_name"]))
    rest = df.iloc[tr_i]
    t2, c2 = next(GroupShuffleSplit(1, test_size=.18, random_state=SEED).split(rest, groups=rest["company_name"]))
    return rest.iloc[t2], rest.iloc[c2], df.iloc[te_i]


def run(data="data/processed/company_year.parquet", models_dir="models", results_dir="results", n_iter=N_ITER, source=None):
    src_file = Path(data).parent / "DATA_SOURCE.txt"
    source = source or (src_file.read_text().strip() if src_file.exists() else "UNKNOWN")
    df = add_features(pd.read_parquet(data)); num = usable_numeric(df); feats = CAT + num
    train, calib, test = split(df)
    print(f"[{source}] features={feats} rows train/calib/test={len(train)}/{len(calib)}/{len(test)} "
          f"companies={train.company_name.nunique()}/{calib.company_name.nunique()}/{test.company_name.nunique()}")
    Path(models_dir).mkdir(exist_ok=True); Path(results_dir).mkdir(exist_ok=True)
    report, comparison = {"data_source": source, "alpha": ALPHA, "features": feats}, []

    for tgt in TARGETS:
        y = lambda d: np.log1p(d[tgt].values)
        fitted, res = {}, {}
        for name, (pipe, grid) in zoo(num).items():
            cv = RandomizedSearchCV(pipe, grid, n_iter=n_iter, cv=GroupKFold(3), scoring="neg_root_mean_squared_error",
                                    random_state=SEED, n_jobs=1)
            cv.fit(train[feats], y(train), groups=train["company_name"])
            fitted[name] = cv.best_estimator_
            m = scores(y(test), cv.best_estimator_.predict(test[feats]))
            m["train_rmse_log"] = scores(y(train), cv.best_estimator_.predict(train[feats]))["rmse_log"]
            m["cv_rmse_log"] = float(-cv.best_score_)
            m["overfit_ratio_test_over_train"] = m["rmse_log"] / m["train_rmse_log"]
            m["overfit_flag"] = bool(m["overfit_ratio_test_over_train"] > 1.5)
            res[name] = m; comparison.append({"target": tgt, "model": name, **m})
            print(f"  {tgt} {name:14s} train={m['train_rmse_log']:.3f} cv={m['cv_rmse_log']:.3f} test={m['rmse_log']:.3f} "
                  f"ratio={m['overfit_ratio_test_over_train']:.2f}{' OVERFIT' if m['overfit_flag'] else ''}")
        base = SectorMedianBaseline().fit(train[feats], y(train)); pb = base.predict(test[feats]); bm = scores(y(test), pb)
        comparison.append({"target": tgt, "model": "sector_median_baseline", **bm})

        best = min(res, key=lambda k: res[k]["cv_rmse_log"])           # chosen on CV only, never on test
        # cross-conformal on train + calibration companies, then ship a model refit on all of them
        dev = pd.concat([train, calib]); ydev = y(dev)
        conf = build_conformal(dev, ydev, oof_predictions(fitted[best], dev, ydev, num), num)
        pipe = clone(fitted[best]).fit(dev[feats], ydev); pt = pipe.predict(test[feats])
        pb = SectorMedianBaseline().fit(dev[feats], ydev).predict(test[feats]); bm = scores(y(test), pb)
        shipped = scores(y(test), pt)
        hw = hw_of(conf, test[feats], test["sector"].values)
        covered = (y(test) >= pt - hw) & (y(test) <= pt + hw)
        sc_ = pd.Series(covered).groupby(test["sector"].values).agg(["mean", "size"]); sc_ = sc_[sc_["size"] >= 20]
        # out-of-time check: train on <=2023 (train companies), score 2024+ (test companies): company- AND time-disjoint
        oot = None
        tr_o, te_o = train[train.year <= 2023], test[test.year >= 2024]
        if len(te_o) >= 100 and len(tr_o) >= 500:
            mo = clone(pipe).fit(tr_o[feats], y(tr_o)); bo = SectorMedianBaseline().fit(tr_o[feats], y(tr_o))
            oot = {"n": int(len(te_o)), "model_rmse_log": scores(y(te_o), mo.predict(te_o[feats]))["rmse_log"],
                   "baseline_rmse_log": scores(y(te_o), bo.predict(te_o[feats]))["rmse_log"]}
        report[tgt] = {
            "best_model": best, "test": {**res[best], "shipped_model_rmse_log": shipped["rmse_log"]}, "baseline_test": bm,
            "improvement_vs_baseline_rmse_pct": float((1 - shipped["rmse_log"] / bm["rmse_log"]) * 100),
            "improvement_95ci_pct": boot_improvement(y(test), pt, pb, test["company_name"].values),
            "interval_method": conf["method"], "interval_selection_scores": conf["selection_interval_scores"],
            "interval_coverage_test": float(covered.mean()), "target_coverage": 1 - ALPHA,
            "sector_coverage_min_n20": {k: float(v) for k, v in sc_["mean"].items()},
            "worst_sector_coverage": float(sc_["mean"].min()), "median_interval_factor": float(np.median(np.exp(2 * hw))),
            "out_of_time_2024plus": oot}
        joblib.dump({"pipeline": pipe, "conformal": conf, "features": feats, "target": tgt, "data_source": source,
                     "model": best, "sectors": sorted(df.sector.unique()), "activities": sorted(df.activity.unique()),
                     "train_range": {"log_turnover": [float(train.log_turnover.min()), float(train.log_turnover.max())],
                                     "year": [int(train.year.min()), int(train.year.max())]}},
                    f"{models_dir}/model_{tgt}.joblib")
        tree = min((k for k in res if k != "ridge"), key=lambda k: res[k]["cv_rmse_log"])   # SHAP needs a tree model
        _plots(tgt, tree, fitted[tree], test, y(test), pt, hw, feats, results_dir)
        print(f"  -> {tgt}: best={best}  vs baseline {report[tgt]['improvement_vs_baseline_rmse_pct']:+.1f}% "
              f"(95% CI {report[tgt]['improvement_95ci_pct'][0]:.1f}..{report[tgt]['improvement_95ci_pct'][1]:.1f})  "
              f"intervals={conf['method']} coverage={covered.mean():.3f} worst-sector={report[tgt]['worst_sector_coverage']:.2f}  OOT={oot}")

    pd.DataFrame(comparison).to_csv(f"{results_dir}/model_comparison.csv", index=False)
    json.dump(report, open(f"{results_dir}/metrics.json", "w"), indent=2)
    return report


def _plots(tgt, tree, pipe, test, y, pt, hw, feats, out):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, shap
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.errorbar(y, pt, yerr=hw, fmt="o", ms=2, alpha=.3, elinewidth=.5); lim = [y.min(), y.max()]; ax.plot(lim, lim, "r--", lw=1)
    ax.set(xlabel=f"actual log1p({tgt}) tCO2e", ylabel="predicted", title=f"{tgt.upper()} held-out companies, 90% conformal band")
    fig.tight_layout(); fig.savefig(f"{out}/pred_vs_actual_{tgt}.png", dpi=150); plt.close(fig)
    X = pipe["p"].transform(test[feats]); sv = shap.TreeExplainer(pipe["m"]).shap_values(X)
    shap.summary_plot(sv, X, feature_names=feats, show=False, plot_size=(8, 4))
    plt.title(f"SHAP ({tree}) for {tgt.upper()}"); plt.tight_layout(); plt.savefig(f"{out}/shap_{tgt}.png", dpi=150); plt.close()


if __name__ == "__main__":
    run()
