"""Seven-day hourly forecasts of demand, solar and wind output from HISTORY ONLY.
At issue time i the model sees data up to i, the calendar and sun geometry of the target hour (astronomy, not weather), and a climatology
learned from training years. It is a statistical forecast, not numerical weather prediction; skill drops with horizon and the metrics say how much."""
import json
from pathlib import Path
import numpy as np, pandas as pd
import lightgbm as lgb
from carbon.microgrid import World

HORIZON = 168
BUCKETS = [(1, 6), (7, 24), (25, 72), (73, 168)]
TARGETS = ("demand", "solar_cf", "wind_cf")
RESIDUAL_BASE = {"wind_cf"}            # wind is persistent for hours: learn a correction to a persistence-to-climatology blend (decay chosen on the calibration year)
TAU_GRID = (8.0, 16.0, 32.0, 64.0, 128.0)
SERIES = {"demand": lambda w: w.demand, "solar_cf": lambda w: w.solar_cf, "wind_cf": lambda w: w.wind_cf}


def _local(w: World):
    return w.times + pd.Timedelta(hours=w.profile.tz_hours)


class Features:
    """Precomputes everything that does not depend on the issue time."""
    def __init__(self, w: World, train_years):
        self.w, loc = w, _local(w)
        self.hod, self.month, self.dow, self.doy = loc.hour.values, loc.month.values, loc.dayofweek.values, loc.dayofyear.values
        self.year = w.times.year.values
        ki = np.where(w.csky > 50, np.clip(w.ghi / np.maximum(w.csky, 1), 0, 1.5), np.nan)
        self.ki24 = pd.Series(ki).rolling(24, min_periods=1).mean().ffill().bfill().values
        self.t_mean24 = pd.Series(w.t2m).rolling(24, min_periods=1).mean().values
        self.train_years = list(train_years)
        self.clim, self.clim_year = {}, {}
        for name in TARGETS:
            y = SERIES[name](w); table = {}
            for yr in self.train_years:
                m = self.year == yr
                df = pd.DataFrame({"mo": self.month[m], "h": self.hod[m], "y": y[m]}).groupby(["mo", "h"]).y.mean()
                table[yr] = df.reindex(pd.MultiIndex.from_product([range(1, 13), range(24)]), fill_value=np.nan).values.reshape(12, 24)
            self.clim_year[name] = table
            self.clim[name] = np.nanmean([table[yr] for yr in self.train_years], axis=0)

    def clim_at(self, name, month, hod, year):
        if year in self.clim_year[name]:            # leave-one-year-out for training years: the target year never feeds its own climatology
            others = [self.clim_year[name][y] for y in self.train_years if y != year]
            return np.nanmean(others, axis=0)[month - 1, hod]
        return self.clim[name][month - 1, hod]

    def build(self, name, issues, hs=None):
        w = self.w; y = SERIES[name](w); hs = np.arange(1, HORIZON + 1) if hs is None else hs
        I = np.asarray(issues)[:, None]; H = hs[None, :]; J = np.minimum(I + H, len(y) - 1)
        csum = np.concatenate([[0], np.cumsum(y)])
        mean24 = (csum[I + 1] - csum[I - 23]) / 24
        same_day = y[J - 24 * np.ceil(H / 24).astype(int)]
        same_week = y[J - 168]
        year_j = self.year[np.minimum(J, len(y) - 1)]
        clim = np.empty(J.shape)
        for yr in np.unique(year_j):
            m = year_j == yr
            clim[m] = self.clim_at(name, self.month[J[m]], self.hod[J[m]], int(yr))
        F = {"h": np.broadcast_to(H, J.shape), "hod": self.hod[J], "dow": self.dow[J],
             "doy_sin": np.sin(2 * np.pi * self.doy[J] / 366), "doy_cos": np.cos(2 * np.pi * self.doy[J] / 366),
             "cur": np.broadcast_to(y[I], J.shape), "mean24": np.broadcast_to(mean24, J.shape), "same_day": same_day, "same_week": same_week,
             "clim": clim, "cs_target": w.csky[J] / 1000.0, "ki24": np.broadcast_to(self.ki24[I], J.shape),
             "t_now": np.broadcast_to(w.t2m[I], J.shape), "t_mean24": np.broadcast_to(self.t_mean24[I], J.shape)}
        X = pd.DataFrame({k: np.asarray(v, dtype=np.float32).ravel() for k, v in F.items()})
        return X, y[J].ravel()


def base_of(name, X, tau=None):
    """Baseline the model corrects: persistence early on, climatology later (only for series where that helps)."""
    if name not in RESIDUAL_BASE or tau is None: return np.zeros(len(X), np.float32)
    w = np.exp(-X["h"].values / tau)
    return (w * X["cur"].values + (1 - w) * X["clim"].values).astype(np.float32)


def _metrics(y, p, h):
    out = {"mae": float(np.mean(np.abs(y - p))), "rmse": float(np.sqrt(np.mean((y - p) ** 2)))}
    for lo, hi in BUCKETS:
        m = (h >= lo) & (h <= hi); out[f"mae_h{lo}-{hi}"] = float(np.mean(np.abs(y[m] - p[m])))
    return out


class Forecaster:
    def __init__(self, world: World, train_years=(2020, 2021, 2022, 2023), cal_year=2024, test_year=2025, issue_every=12, seed=42):
        self.w, self.train_years, self.cal_year, self.test_year, self.issue_every, self.seed = world, tuple(train_years), cal_year, test_year, issue_every, seed
        self.F = Features(world, self.train_years); self.models, self.q, self.alpha, self.tau, self.beta = {}, {}, {}, {}, {}; self.metrics = {}

    def _issues(self, years):
        yr = self.w.times.year.values
        ok = np.where(np.isin(yr, list(years)))[0]
        ok = ok[(ok >= 200) & (ok + HORIZON < len(yr))]
        return ok[::self.issue_every]

    def fit(self):
        for name in TARGETS:
            X, y = self.F.build(name, self._issues(self.train_years))
            m = lgb.LGBMRegressor(n_estimators=350, learning_rate=0.05, num_leaves=63, min_child_samples=60, subsample=0.8, subsample_freq=1,
                                  colsample_bytree=0.9, reg_lambda=2.0, random_state=self.seed, n_jobs=4, verbose=-1)
            tau = None
            if name in RESIDUAL_BASE:
                Xc0, yc0 = self.F.build(name, self._issues([self.cal_year]))
                tau = min(TAU_GRID, key=lambda t: np.mean(np.abs(yc0 - base_of(name, Xc0, t))))
            self.tau[name] = tau
            m.fit(X, y - base_of(name, X, tau)); self.models[name] = m
            # a per-horizon shrink factor fitted on the calibration year keeps the model from adding noise where the baseline is already good
            Xc, yc = self.F.build(name, self._issues([self.cal_year])); b = base_of(name, Xc, tau)
            rhat = m.predict(Xc).reshape(-1, HORIZON); d = (yc - b).reshape(-1, HORIZON)
            k = 9; smooth = lambda a: np.convolve(np.pad(a, (k // 2, k // 2), mode="edge"), np.ones(k) / k, mode="valid")
            alpha = np.clip(smooth((rhat * d).sum(0) / np.maximum((rhat ** 2).sum(0), 1e-12)), 0, 1)
            self.alpha[name] = alpha
            pre = alpha * rhat
            if name in RESIDUAL_BASE:                                         # blend towards persistence where it is still the better short-range guess
                cur = Xc["cur"].values.reshape(-1, HORIZON); e = cur - (b.reshape(-1, HORIZON) + pre); d2 = yc.reshape(-1, HORIZON) - (b.reshape(-1, HORIZON) + pre)
                self.beta[name] = np.clip(smooth((d2 * e).sum(0) / np.maximum((e ** 2).sum(0), 1e-12)), 0, 1)
                pre = pre + self.beta[name] * e
            else:
                self.beta[name] = np.zeros(HORIZON)
            r = d - pre                                                       # calibration residuals of the final forecast
            self.q[name] = (smooth(np.percentile(r, 20, axis=0)), smooth(np.percentile(r, 80, axis=0)))
        return self

    def evaluate(self):
        res = {}
        for name in TARGETS:
            X, y = self.F.build(name, self._issues([self.test_year])); h = X["h"].values
            hh = h.astype(int) - 1
            pred = np.clip(self._final(name, X), 0, None)
            lo, hi = self.q[name]
            cover = float(np.mean((y >= pred + lo[hh]) & (y <= pred + hi[hh])))
            res[name] = {"lightgbm": _metrics(y, pred, h), "persistence": _metrics(y, X["cur"].values, h), "seasonal_naive_24h": _metrics(y, X["same_day"].values, h),
                         "climatology": _metrics(y, X["clim"].values, h), "band_coverage_p20_p80": cover, "n": int(len(y)), "mean_actual": float(y.mean())}
            for base in ("persistence", "seasonal_naive_24h"):
                res[name][f"skill_vs_{base}"] = float(1 - res[name]["lightgbm"]["mae"] / res[name][base]["mae"])
        self.metrics = res
        return res

    def _final(self, name, X):
        hh = X["h"].values.astype(int) - 1
        pre = base_of(name, X, self.tau[name]) + self.alpha[name][hh] * self.models[name].predict(X)
        return pre + self.beta[name][hh] * (X["cur"].values - pre)

    # ---- operational use: one issue time, 168 hourly values
    def predict(self, i, method="lightgbm", band=None):
        out = {}
        for name in TARGETS:
            X, _ = self.F.build(name, [i])
            if method == "lightgbm":
                p = np.clip(self._final(name, X), 0, None)
                if band == "conservative":                              # lower renewables, higher demand
                    lo, hi = self.q[name]; p = np.clip(p + (hi if name == "demand" else lo), 0, None)
            elif method == "persistence": p = X["cur"].values
            else: p = X["same_day"].values
            out[name] = np.clip(p, 0, 1 if name != "demand" else None)
        return out

    def save(self, path):
        import joblib
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"models": self.models, "q": self.q, "alpha": self.alpha, "beta": self.beta, "tau": self.tau, "train_years": self.train_years}, path)
