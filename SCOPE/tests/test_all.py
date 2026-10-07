import numpy as np, pytest
from carbon import calculator as C, scope3 as S3, abatement as A, data_synth
from carbon.train import conformal_table, half_width


def test_diesel_polaris_example():
    assert abs(C.scope1({"diesel_l": 22500}) - 60.75) < 1e-6


def test_scope2_cea():
    assert abs(C.scope2(1_000_000) - 675.0) < 1e-6


def test_useeio_loaded_and_scope3_positive():
    assert S3.scope3({"steel": 8.5e7}) > 0
    assert abs(S3.ef_kg_per_inr("steel") * 85 - 0.787) < 1e-9          # USEEIO v1.3 NAICS 331110 with margins


def test_monte_carlo_brackets_point_estimate():
    fu, sp = {"diesel_l": 50000}, {"freight": 1e7}
    fp, mc = C.footprint(fu, 1e6, sp), C.monte_carlo(fu, 1e6, sp, n=4000)
    assert mc["total"]["p5"] < fp.total_t < mc["total"]["p95"] * 1.2
    assert mc["scope3"]["p95"] > mc["scope3"]["p5"] * 1.5               # wide Scope 3 uncertainty


def test_conformal_coverage_on_synthetic_noise():
    rng = np.random.default_rng(0)
    sec = np.array(["a"] * 4000)
    tab = conformal_table(np.abs(rng.normal(0, 1, 4000)), sec)
    test_res = np.abs(rng.normal(0, 1, 20000))
    assert abs((test_res <= half_width(tab, ["a"] * 20000)).mean() - 0.90) < 0.02


def test_macc_sorted_and_negative_cost_for_polaris():
    lev = A.build_levers(84000, 500000, 300, solar_kwh=150000, ppa_share=0.2)
    m = A.macc(lev)
    assert m.cost_inr_per_t.is_monotonic_increasing
    assert m.loc[m.name.str.contains("Polaris"), "cost_inr_per_t"].iloc[0] < 0


def test_pathway_levers_reduce_emissions():
    lev = A.build_levers(84000, 500000, 300, solar_kwh=150000)
    p = A.pathway(226, 337, 300, lev, n=500)
    assert (p.with_levers_p50 <= p.bau_p50 + 1e-9).all() and A.cumulative_abated(p) > 0


def test_synthetic_generator_schema():
    d = data_synth.generate(50)
    assert {"s1", "s2", "turnover_cr", "sector", "activity"} <= set(d.columns) and (d.s1 > 0).all()


def test_solar_plus_ppa_never_exceeds_grid_emissions():
    lev = A.build_levers(0, 500_000, 0, solar_kwh=400_000, ppa_share=0.5, supplier_cut=0)
    assert sum(l.abatement_t for l in lev if l.scope == 2) <= C.scope2(500_000) + 1e-9


def test_td_loss_and_validation():
    assert abs(C.scope2(1000, td_loss=0.2) - C.scope2(1000) / 0.8) < 1e-9
    with pytest.raises(ValueError): C.scope2(1000, td_loss=1.0)
    with pytest.raises(KeyError): C.scope1({"diesell": 5})


def test_training_runs_on_all_nan_optional_features(tmp_path, monkeypatch):
    """Real BRSR has no employees / renewable_share: pipeline must adapt, not crash."""
    from carbon import train as T, predict as P
    d = data_synth.generate(220, seed=1); d["employees"] = np.nan; d["renewable_share"] = np.nan
    f = tmp_path / "company_year.parquet"; d.to_parquet(f)
    (tmp_path / "models").mkdir(); (tmp_path / "results").mkdir()
    rep = T.run(str(f), str(tmp_path / "models"), str(tmp_path / "results"), n_iter=2, source="TEST")
    assert "log_employees" not in rep["features"] and "renewable_share" not in rep["features"]
    out = P.predict("Cement", "Cement / type 1", 2000, models_dir=str(tmp_path / "models"))
    assert out["s1"]["lo"] < out["s1"]["point"] < out["s1"]["hi"]
    far = P.predict("Cement", "Cement / type 1", 2000, year=2040, models_dir=str(tmp_path / "models"))
    assert any("outside the training" in w for w in far["warnings"])
