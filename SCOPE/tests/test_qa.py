"""Hard QA: validation, invariants (property-based), ML leakage / negative control / fresh-data checks,
adapter on BRSR-shaped input, determinism, and app fuzzing. Run: pytest -q"""
import math, os
from pathlib import Path
import numpy as np, pandas as pd, pytest
from hypothesis import given, settings, strategies as st
from carbon import calculator as C, scope3 as S3, abatement as A, data_synth

ROOT = Path(__file__).resolve().parents[1]
HAS_MODELS = (ROOT / "models" / "model_s1.joblib").exists() and (ROOT / "models" / "model_s2.joblib").exists()
needs_models = pytest.mark.skipif(not HAS_MODELS, reason="run `make train` first")
pos = st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False)
frac = st.floats(min_value=0, max_value=1, allow_nan=False)


# ------------------------------------------------------------------ input validation
@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf")])
def test_calculator_rejects_bad_numbers(bad):
    with pytest.raises(ValueError): C.scope1({"diesel_l": bad})
    with pytest.raises(ValueError): C.scope2(bad)
    with pytest.raises(ValueError): S3.scope3({"steel": bad})


def test_scope3_unknown_category_and_empty():
    with pytest.raises(KeyError): S3.scope3({"unobtainium": 1e6})
    assert S3.scope3({}) == 0.0 and C.monte_carlo({"diesel_l": 0}, 0, {})["total"]["p95"] == 0.0


@pytest.mark.parametrize("kw", [dict(diesel_saved_frac=1.5), dict(ppa_share=2.0), dict(supplier_cut=3.0), dict(diesel_saved_frac=-0.1)])
def test_levers_reject_fractions_outside_0_1(kw):
    with pytest.raises(ValueError): A.build_levers(1000, 1000, 100, **kw)


def test_abatement_degenerate_inputs_do_not_crash():
    assert A.macc([]).empty
    assert (A.pathway(1, 1, 1, [], n=30).with_levers_p50 == A.pathway(1, 1, 1, [], n=30).bau_p50).all()
    with pytest.raises(ValueError): A.pathway(1, 1, 1, [], adoption_years=0)
    with pytest.raises(ValueError): A.pathway(1, 1, 1, [], start=2030, end=2026)


# ------------------------------------------------------------------ independent recomputation
def test_hand_computed_reference_case():
    fp = C.footprint({"diesel_l": 84_000}, 500_000, {"steel": 5e7})
    steel_ef = 0.787 / 85                                  # USEEIO kg/USD -> kg/INR
    assert math.isclose(fp.scope1_t, 84_000 * 2.70 / 1000, rel_tol=1e-12)
    assert math.isclose(fp.scope2_t, 500_000 * 0.675 / 1000, rel_tol=1e-12)
    assert math.isclose(fp.scope3_t, 5e7 * steel_ef / 1000, rel_tol=1e-9)


def test_useeio_file_integrity():
    t = S3.load_useeio()
    assert len(t) == 1016 and t.notna().all() and (t > 0).all() and t.index.is_unique
    assert all(c[0] in t.index for c in S3.CATEGORIES.values())


# ------------------------------------------------------------------ properties
@settings(max_examples=60, deadline=None)
@given(d=pos, k=pos, s=pos, m=st.floats(0.1, 10))
def test_footprint_is_linear_and_nonnegative(d, k, s, m):
    a = C.footprint({"diesel_l": d}, k, {"freight": s})
    b = C.footprint({"diesel_l": d * m}, k * m, {"freight": s * m})
    assert a.total_t >= 0 and math.isclose(b.total_t, a.total_t * m, rel_tol=1e-9, abs_tol=1e-9)


@settings(max_examples=40, deadline=None)
@given(d=st.floats(1, 1e7), k=st.floats(1, 1e8), s=st.floats(1, 1e9))
def test_monte_carlo_ordering_and_mean_preserving(d, k, s):
    mc = C.monte_carlo({"diesel_l": d}, k, {"steel": s}, n=2000)
    for v in mc.values(): assert v["p5"] <= v["p50"] <= v["p95"]
    assert mc["total"]["p5"] <= C.footprint({"diesel_l": d}, k, {"steel": s}).total_t <= mc["total"]["p95"] * 1.3


@settings(max_examples=50, deadline=None)
@given(d=st.floats(0, 1e6), k=st.floats(0, 1e7), s3=st.floats(0, 1e4), sf=frac, sol=st.floats(0, 2e7), ppa=frac, sup=frac)
def test_levers_never_abate_more_than_the_baseline(d, k, s3, sf, sol, ppa, sup):
    lev = A.build_levers(d, k, s3, sf, solar_kwh=sol, ppa_share=ppa, supplier_cut=sup)
    base = {1: C.scope1({"diesel_l": d}), 2: C.scope2(k), 3: s3}
    for sc in (1, 2, 3):
        assert sum(l.abatement_t for l in lev if l.scope == sc) <= base[sc] + 1e-9
    m = A.macc(lev)
    assert m.cost_inr_per_t.is_monotonic_increasing and (m.abatement_t >= 0).all()


@settings(max_examples=15, deadline=None)
@given(d=st.floats(1, 1e6), k=st.floats(1, 1e7), s3=st.floats(1, 1e4))
def test_pathway_with_levers_never_above_bau(d, k, s3):
    lev = A.build_levers(d, k, s3, solar_kwh=k / 2, ppa_share=.3)
    p = A.pathway(C.scope1({"diesel_l": d}), C.scope2(k), s3, lev, n=200)
    assert (p.with_levers_p50 <= p.bau_p50 + 1e-6).all() and (p.with_levers_p50 >= 0).all()
    assert p.year.is_monotonic_increasing and p.year.iloc[0] == 2026 and p.year.iloc[-1] == 2050


# ------------------------------------------------------------------ ML: leakage, negative control, fresh data
def _frames():
    from carbon import train as T
    df = T.add_features(pd.read_parquet(ROOT / "data/processed/company_year.parquet"))
    return T, df, *T.split(df)


@needs_models
def test_no_company_in_two_splits():
    _, df, tr, ca, te = _frames()
    s = [set(x.company_name) for x in (tr, ca, te)]
    assert not (s[0] & s[1] or s[0] & s[2] or s[1] & s[2]) and len(tr) + len(ca) + len(te) == len(df)


@needs_models
def test_shuffled_labels_destroy_skill_negative_control():
    from sklearn.metrics import mean_squared_error
    T, df, tr, ca, te = _frames(); num = T.usable_numeric(df)
    trs = tr.copy(); trs["s1"] = np.random.default_rng(0).permutation(trs["s1"].values)
    pipe, _ = T.zoo(num)["lightgbm"]; pipe.fit(trs[T.CAT + num], np.log1p(trs.s1))
    y = np.log1p(te.s1.values); rmse = np.sqrt(mean_squared_error(y, pipe.predict(te[T.CAT + num])))
    assert rmse > 0.9 * y.std()                                   # real model gets ~0.55 vs std ~3.0


@needs_models
def test_generalises_to_a_fresh_synthetic_world_and_intervals_cover():
    import joblib
    from sklearn.metrics import mean_squared_error
    T, df, tr, *_ = _frames(); new = T.add_features(data_synth.generate(500, seed=999))
    for tgt in ("s1", "s2"):
        b = joblib.load(ROOT / f"models/model_{tgt}.joblib"); X, y = new[b["features"]], np.log1p(new[tgt].values)
        p = b["pipeline"].predict(X); hw = T.hw_of(b["conformal"], X, new["sector"].values)
        base = T.SectorMedianBaseline().fit(tr[b["features"]], np.log1p(tr[tgt].values)).predict(X)
        assert np.sqrt(mean_squared_error(y, p)) < 0.75 * np.sqrt(mean_squared_error(y, base))
        assert 0.85 <= np.mean(np.abs(y - p) <= hw) <= 0.97


@needs_models
def test_predict_rejects_garbage_and_orders_interval():
    from carbon import predict as P
    for bad in (0, -5, float("nan"), float("inf")):
        with pytest.raises(ValueError): P.predict("Cement", "Cement / type 1", bad)
    with pytest.raises(ValueError): P.predict("Cement", "Cement / type 1", 100, renewable_share=1.5)
    o = P.predict("Cement", "Cement / type 1", 2000)
    for t in ("s1", "s2"): assert 0 < o[t]["lo"] < o[t]["point"] < o[t]["hi"]
    assert any("outside the training" in w for w in P.predict("Cement", "Cement / type 1", 2000, year=1990)["warnings"])
    assert any("unseen" in w for w in P.predict("Space Mining", "x", 2000)["warnings"])


@needs_models
def test_directional_sanity():
    from carbon import predict as P
    p = lambda **k: P.predict(**{"sector": "Textiles", "activity": "Textiles / type 1", "turnover_cr": 3000, **k})
    assert p(turnover_cr=15000)["s1"]["point"] > 3 * p()["s1"]["point"]
    assert p(renewable_share=0.8)["s2"]["point"] < p(renewable_share=0.05)["s2"]["point"]
    assert P.predict("Power Generation", "Power Generation / type 1", 3000)["s1"]["point"] > 100 * P.predict("IT Services", "IT Services / type 1", 3000)["s1"]["point"]


def test_training_is_deterministic(tmp_path):
    from carbon import train as T
    d = data_synth.generate(220, seed=5); f = tmp_path / "c.parquet"; d.to_parquet(f)
    out = []
    for i in range(2):
        m, r = tmp_path / f"m{i}", tmp_path / f"r{i}"; m.mkdir(); r.mkdir()
        out.append(T.run(str(f), str(m), str(r), n_iter=2, source="TEST"))
    assert out[0]["s1"]["test"] == out[1]["s1"]["test"] and out[0]["s2"]["interval_coverage_test"] == out[1]["s2"]["interval_coverage_test"]


# ------------------------------------------------------------------ BRSR adapter on realistic wording
def test_brsr_adapter_recovers_turnover_from_combined_intensity(tmp_path, monkeypatch):
    from carbon import prepare_brsr as B
    d = data_synth.generate(40, seed=3); rows = []
    for _, r in d.iterrows():
        base = dict(company_name=r.company_name, cin_number="X", main_business_activity=r.activity, sector=r.sector,
                    start_date=f"{int(r.year)}-04-01", end_date=f"{int(r.year) + 1}-03-31")
        rows += [dict(base, type_of_emissions="Total Scope 1 emissions (Break-up of the GHG into CO2, CH4, N2O, HFCs, PFCs, SF6, NF3, if available)", value=r.s1, unit="Metric tonnes of CO2 equivalent"),
                 dict(base, type_of_emissions="Total Scope 2 emissions (Break-up of the GHG into CO2, CH4, N2O, HFCs, PFCs, SF6, NF3, if available)", value=r.s2, unit="Metric tonnes of CO2 equivalent"),
                 dict(base, type_of_emissions="Total Scope 1 and Scope 2 emissions per rupee of turnover", value=(r.s1 + r.s2) / (r.turnover_cr * 1e7), unit="tCO2e per rupee")]
    (tmp_path / "data/processed").mkdir(parents=True); pd.DataFrame(rows).to_csv(tmp_path / "b.csv", index=False)
    monkeypatch.chdir(tmp_path); B.main("b.csv")
    out = pd.read_parquet("data/processed/company_year.parquet"); out["year"] -= 1      # fiscal year ends in the next calendar year
    m = out.merge(d, on=["company_name", "year"], suffixes=("_a", "_t"))
    assert len(m) == len(d) and np.allclose(m.turnover_cr_a, m.turnover_cr_t, rtol=1e-6)


# ------------------------------------------------------------------ app fuzz
@needs_models
def test_app_survives_extreme_and_zero_inputs():
    from streamlit.testing.v1 import AppTest
    os.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    rng = np.random.default_rng(0)
    for mode in ["min", "max", "min"] + ["rand"] * 6:
        for w in list(at.number_input):
            v = {"min": w.min, "max": w.max}.get(mode, w.min + (w.max - w.min) * float(rng.random()) ** 4)
            w.set_value(type(w.value)(min(max(v, w.min), w.max)))
        for w in at.slider:
            w.set_value({"min": w.min, "max": w.max}.get(mode, w.min + (w.max - w.min) * float(rng.random())))
        at.run()
        assert not at.exception, (mode, at.exception[0].value)
    sec = [s for s in at.selectbox if s.label == "Sector"][0]
    for s in sec.options:
        sec.set_value(s); at.run(); assert not at.exception, (s, at.exception[0].value)
