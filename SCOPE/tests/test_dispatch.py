"""Dispatch engine: physics, the MILP's constraints, forecast honesty, simulation bookkeeping and the published results."""
import json
from pathlib import Path
import numpy as np, pandas as pd, pytest
from carbon import forecast as F, microgrid as M, milp, simulate as S, weather as W

ROOT = Path(__file__).resolve().parents[1]
have_weather = all((W.CACHE / f"{k}_{y}.parquet").exists() for k in M.PROFILES for y in range(2020, 2026))
pytestmark = pytest.mark.skipif(not have_weather, reason="weather cache missing: run `python -m carbon.dispatch_eval` once with network access")


@pytest.fixture(scope="module")
def worlds():
    return {k: M.build_world(p, W.load_weather(p)) for k, p in M.PROFILES.items()}


@pytest.fixture(scope="module")
def forecaster(worlds):
    return F.Forecaster(worlds["polar"]).fit()


# ------------------------------------------------------------------ physics
def test_sun_geometry_polar_night_and_midnight_sun(worlds):
    w = worlds["polar"]; june = w.times.month == 6; dec = w.times.month == 12
    assert (w.csky[june] == 0).mean() > 0.95 and (w.csky[dec] > 0).mean() > 0.9              # 70S: dark in June, sun all day in December
    leh = worlds["community"]; assert 800 < leh.csky.max() < 1150 and leh.pv.max() <= M.COMMUNITY.pv_kwp
    assert (w.pv[w.ghi == 0] == 0).all() and (w.pv >= 0).all() and w.pv.max() <= M.POLAR.pv_kwp


def test_wind_power_curve():
    p = M.POLAR; v = np.array([0, 2.9, 3.0, 6, 9, 12, 15, 24.9, 25.0, 40]) / (p.wind_hub_m / 100) ** 0.14
    out = M.wind_power_kw(p, v)
    assert out[0] == 0 and out[1] == 0 and out[-1] == 0 and out[-2] == 0                       # below cut-in, above cut-out
    assert np.all(np.diff(out[2:6]) > 0) and out[5] == pytest.approx(p.wind_kw * p.wind_avail) and out[6] == out[5]


def test_demand_is_simulated_cold_driven_and_floored(worlds):
    w = worlds["polar"]; assert w.demand.min() >= 0.3 * M.POLAR.base_kw and np.corrcoef(w.demand, w.t2m)[0, 1] < -0.4


# ------------------------------------------------------------------ MILP
def _window(w, start, H=72):
    i = w.idx(start); p = w.profile; D = w.demand[i:i + H]
    return p, dict(essential=p.essential_frac * D, normal=p.normal_frac * D, flex_base=p.flexible_frac * D, pv=w.pv[i:i + H], wind=w.wind[i:i + H]), D


@pytest.mark.parametrize("start", ["2025-06-02", "2025-12-18"])
@pytest.mark.parametrize("mode", ["economy", "green"])
def test_milp_respects_every_physical_constraint(worlds, start, mode):
    p, kw, D = _window(worlds["polar"], start); soc0 = 0.5 * p.battery_kwh
    pl = milp.solve_window(p, soc0_kwh=soc0, mode=mode, fuel_stock_l=5000, **kw)
    load = kw["essential"] + kw["normal"] - pl.shed + pl.flex
    assert np.abs(pl.g + pl.pv_used + pl.wind_used + pl.discharge - pl.charge + pl.unmet - load).max() < 1e-6                 # energy balance
    on = pl.u > .5
    assert (pl.g[on] >= p.gen_min_kw - 1e-6).all() and (pl.g <= p.gen_kw + 1e-6).all() and (pl.g[~on] < 1e-6).all()         # generator limits
    assert (pl.soc >= p.soc_min * p.battery_kwh - 1e-6).all() and (pl.soc <= p.soc_max * p.battery_kwh + 1e-6).all()
    prev = np.r_[soc0, pl.soc[:-1]]; assert np.abs(pl.soc - (prev + p.eta_c * pl.charge - pl.discharge / p.eta_d)).max() < 1e-6   # battery book-keeping
    assert np.minimum(pl.charge, pl.discharge).max() < 1e-6                                                                    # never both at once
    assert (pl.pv_used <= kw["pv"] + 1e-9).all() and (pl.wind_used <= kw["wind"] + 1e-9).all() and pl.fuel_l.sum() <= 5000
    assert pl.unmet.sum() < 1e-6                                                                                              # feasible case: nothing unserved
    for b in range(0, len(D), p.flex_window_h):                                                                                # flexible energy is conserved in each block
        blk = slice(b, b + p.flex_window_h); assert pl.flex[blk].sum() == pytest.approx(kw["flex_base"][blk].sum(), abs=1e-5)


def test_milp_shows_unmet_when_physically_impossible(worlds):
    p, kw, D = _window(worlds["polar"], "2025-06-02", 24); kw["pv"] = kw["pv"] * 0; kw["wind"] = kw["wind"] * 0
    pl = milp.solve_window(p, soc0_kwh=p.soc_min * p.battery_kwh, mode="economy", fuel_stock_l=0.0, **kw)
    assert pl.g.sum() < 1e-6 and pl.unmet.sum() + pl.shed.sum() > 0.9 * (kw["essential"] + kw["normal"]).sum()


def test_survival_budget_is_a_hard_limit_and_rations_nonessential_first(worlds):
    p, kw, D = _window(worlds["polar"], "2025-06-02", 72)
    free = milp.solve_window(p, soc0_kwh=0.6 * p.battery_kwh, mode="survival", fuel_stock_l=5000, flex_curtail_frac=1.0, **kw)
    cap = 0.5 * free.fuel_l.sum()
    tight = milp.solve_window(p, soc0_kwh=0.6 * p.battery_kwh, mode="survival", fuel_stock_l=5000, fuel_budget_l=cap, flex_curtail_frac=1.0, **kw)
    assert tight.fuel_l.sum() <= cap + 1e-6 and tight.shed.sum() + tight.flex_curtailed_kwh > free.shed.sum() + free.flex_curtailed_kwh
    hit = tight.unmet > 1e-6                                                                  # essential load is short only in hours where all normal load is already shed
    assert (tight.shed[hit] >= kw["normal"][hit] - 1e-6).all()
    mild = milp.solve_window(p, soc0_kwh=0.6 * p.battery_kwh, mode="survival", fuel_stock_l=5000, fuel_budget_l=0.9 * free.fuel_l.sum(), flex_curtail_frac=1.0, **kw)
    assert mild.unmet.sum() <= 1e-6                                                          # a mild budget is met by rationing non-essential load alone


# ------------------------------------------------------------------ forecasts
def test_forecast_is_causal(worlds, forecaster):
    w = worlds["polar"]; i = w.idx("2025-04-10") ; base = forecaster.predict(i)
    keys = ("demand", "solar_cf", "wind_cf", "t2m", "ghi", "pv", "wind")
    saved = {k: getattr(w, k) for k in keys}
    for k in keys: setattr(w, k, np.array(saved[k]))                                         # writable copies; originals are restored below
    try:
        for k in keys: getattr(w, k)[i + 1:] = getattr(w, k)[i + 1:] * 7 + 123              # rewrite the whole future
        orig_ki, orig_tm = forecaster.F.ki24, forecaster.F.t_mean24
        forecaster.F.ki24 = np.array(orig_ki); forecaster.F.t_mean24 = np.array(orig_tm)
        forecaster.F.ki24[i + 1:] = 0.123; forecaster.F.t_mean24[i + 1:] = 99
        again = forecaster.predict(i)
    finally:
        for k, v in saved.items(): setattr(w, k, v)
        forecaster.F.ki24, forecaster.F.t_mean24 = orig_ki, orig_tm
    for k in base: np.testing.assert_allclose(base[k], again[k], atol=1e-6, err_msg=f"{k} forecast depends on data after the issue time")


def test_trained_forecast_beats_simple_baselines_on_unseen_year(forecaster):
    m = forecaster.evaluate()
    for name in ("demand", "solar_cf", "wind_cf"):
        assert m[name]["lightgbm"]["mae"] < m[name]["seasonal_naive_24h"]["mae"] and m[name]["lightgbm"]["mae"] < m[name]["persistence"]["mae"]
        assert 0.45 < m[name]["band_coverage_p20_p80"] < 0.75                              # a P20-P80 band should hold roughly 60%
    assert set(forecaster.train_years) == {2020, 2021, 2022, 2023} and forecaster.test_year == 2025


def test_forecast_shapes_and_bounds(worlds, forecaster):
    fc = forecaster.predict(worlds["polar"].idx("2025-02-01"))
    assert all(len(v) == 168 for v in fc.values()) and fc["solar_cf"].max() <= 1 and fc["wind_cf"].min() >= 0 and fc["demand"].min() >= 0
    cons = forecaster.predict(worlds["polar"].idx("2025-02-01"), band="conservative")
    assert cons["demand"].mean() >= fc["demand"].mean() and cons["wind_cf"].mean() <= fc["wind_cf"].mean() + 1e-9


# ------------------------------------------------------------------ simulation
@pytest.mark.parametrize("scenario", ["A", "C"])
def test_simulation_conserves_energy_and_fuel(worlds, forecaster, scenario):
    w = worlds["polar"]; p = w.profile
    r = S.simulate(w, forecaster, scenario, "economy", "2025-06-03", 3, fuel0=2000.0); s = r.series
    bal = s.gen + s.pv_used + s.wind_used + s.discharge - s.charge + s.unmet - s.firm_served - s.flex_served - s.dump
    assert np.abs(bal).max() < 1e-6
    assert (s.fuel_stock >= -1e-6).all() and s.fuel_l.sum() == pytest.approx(2000.0 - s.fuel_stock.iloc[-1], abs=1e-6)
    assert (s.soc >= p.soc_min * p.battery_kwh - 1e-3).all() and (s.soc <= p.soc_max * p.battery_kwh + 1e-3).all()
    assert (s.pv_used <= s.pv_avail + 1e-9).all() and (s.wind_used <= s.wind_avail + 1e-9).all() and (s.demand == w.demand[w.idx("2025-06-03"):][:72]).all()


def test_empty_tank_means_no_generator_and_visible_unmet(worlds, forecaster):
    r = S.simulate(worlds["polar"], forecaster, "A", "economy", "2025-06-03", 2, fuel0=0.0)
    assert r.series.gen.sum() == 0 and r.metrics["unmet_kwh"] > 0 and r.metrics["fuel_l"] == 0


def test_simulation_is_deterministic(worlds, forecaster):
    a = S.simulate(worlds["polar"], forecaster, "A", "economy", "2025-09-01", 4).metrics; b = S.simulate(worlds["polar"], forecaster, "A", "economy", "2025-09-01", 4).metrics
    assert a == b


def test_window_too_close_to_the_end_of_data_is_refused(worlds, forecaster):
    with pytest.raises(ValueError, match="week before"): S.simulate(worlds["polar"], forecaster, "C", "economy", "2025-12-29", 2)


# ------------------------------------------------------------------ published results
@pytest.mark.skipif(not (ROOT / "results/dispatch/polar.json").exists(), reason="run `python -m carbon.dispatch_eval` first")
@pytest.mark.parametrize("key", ["polar", "community"])
def test_published_results_are_internally_consistent(key):
    f = ROOT / "results/dispatch" / f"{key}.json"
    if not f.exists(): pytest.skip("profile not evaluated yet")
    d = json.loads(f.read_text()); sc = d["scenarios"]
    assert sc["A"]["solves"] == 0 and sc["C"]["solves"] > 300
    assert sc["A"]["demand_kwh"] == pytest.approx(sc["B"]["demand_kwh"]) == pytest.approx(sc["C"]["demand_kwh"])           # same load, same weather, same hardware
    for k in ("A", "B", "C"):
        assert sum(d["monthly"][k]["fuel_l"]) == pytest.approx(sc[k]["fuel_l"], rel=2e-3)
        assert sc[k]["unmet_kwh"] <= 0.001 * sc[k]["demand_kwh"] and len(d["weeks"][k]) == 12 and len(d["weeks"][k][0]["gen"]) == 168
    st = d["stress"]["scenarios"]
    assert st["C-survival"]["essential_unmet_kwh"] <= st["A"]["essential_unmet_kwh"] and st["C-survival"]["essential_unmet_kwh"] <= st["C-economy"]["essential_unmet_kwh"] + 1e-6
    assert d["forecast"]["demand"]["skill_vs_seasonal_naive_24h"] > 0
