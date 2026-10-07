"""Tests for the uncertainty drivers, the fuel runway planner and the stress report."""
import json
from pathlib import Path
import numpy as np, pytest
from carbon import calculator as C, runway as R, scope3 as S3

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- uncertainty drivers
def test_driver_shares_sum_to_one_and_rank_by_size():
    d = C.drivers({"diesel_l": 1000}, 1000, {"steel": 5e8, "it_services": 1e6}, top=99, n=20000)
    assert abs(sum(r["share"] for r in d) - 1) < 0.03                      # independent terms: exact up to Monte-Carlo noise
    assert d[0]["name"].startswith("Iron") and d[0]["share"] > 0.9
    assert [r["share"] for r in d] == sorted((r["share"] for r in d), reverse=True)


def test_drivers_edge_cases():
    assert C.drivers({"diesel_l": 0}, 0, {}) == []
    with pytest.raises(ValueError): C.drivers({"diesel_l": -1}, 0, {})
    with pytest.raises(KeyError): C.drivers({}, 0, {"nope": 1})


def test_scope3_total_unchanged_by_terms_refactor():
    spend = {"steel": 1e7, "freight": 2e7}
    a = S3.monte_carlo(spend, np.random.default_rng(7), 500)
    b = sum(S3.monte_carlo_terms(spend, np.random.default_rng(7), 500).values())
    assert np.allclose(a, b)


# ---------------------------------------------------------------- fuel runway
def test_runway_is_deterministic_and_ordered():
    a, b = R.runway(20000, 1000, 25, saving_frac=0.268), R.runway(20000, 1000, 25, saving_frac=0.268)
    assert a == b
    for k in ("baseline", "with_saving"):
        lo, mid, hi = a["runway_days"][k]; assert lo <= mid <= hi
    assert a["p_ok_at_delivery"]["with_saving"] >= a["p_ok_at_delivery"]["baseline"]


def test_runway_monotonicity():
    p = lambda **k: R.runway(**{"stock_l": 20000, "daily_l": 1000, "delivery_day": 25, **k})["p_ok_with_delay"]["baseline"]
    assert p(stock_l=26000) >= p() >= p(stock_l=16000)                      # more fuel never hurts
    assert p(delay_days=0) >= p(delay_days=5) >= p(delay_days=12)           # later delivery never helps
    curve = R.runway(20000, 1000, 25)["delay_curve"]["baseline"]
    assert all(curve[i] >= curve[i + 1] - 1e-12 for i in range(len(curve) - 1))


def test_delay_curve_agrees_with_running_the_scenario_directly():
    r = R.runway(20000, 1000, 25, saving_frac=0.268)
    assert r["delay_curve"]["baseline"][0] == r["p_ok_at_delivery"]["baseline"]
    for k in (0, 1, 3, 6):
        direct = R.runway(20000, 1000, 25, saving_frac=0.268, delay_days=k)["p_ok_with_delay"]
        assert r["delay_curve"]["baseline"][k] == direct["baseline"] and r["delay_curve"]["with_saving"][k] == direct["with_saving"]


def test_saving_needed_is_zero_exactly_when_the_plan_already_clears_the_target():
    ok = R.runway(30000, 1000, 25); assert ok["p_ok_at_delivery"]["baseline"] >= ok["target_p"] and ok["saving_needed_for_target"] == 0.0
    no = R.runway(20000, 1000, 25); assert no["p_ok_at_delivery"]["baseline"] < no["target_p"] and no["saving_needed_for_target"] > 0


def test_saving_needed_actually_reaches_the_target():
    r = R.runway(20000, 1000, 25)
    need = r["saving_needed_for_target"]; assert need is not None and 0 < need < 0.9
    again = R.runway(20000, 1000, 25, saving_frac=need + 0.002)
    assert again["p_ok_at_delivery"]["with_saving"] >= r["target_p"] - 0.01


def test_runway_extremes():
    easy = R.runway(1e6, 1000, 25); assert easy["p_ok_at_delivery"]["baseline"] == 1 and easy["saving_needed_for_target"] == 0
    hopeless = R.runway(2000, 1000, 25); assert hopeless["p_ok_at_delivery"]["baseline"] == 0 and hopeless["saving_needed_for_target"] is None
    flat = R.runway(20000, 1000, 25, cv=0)                                 # no variability: runway is exactly stock / daily
    assert flat["runway_days"]["baseline"] == [20, 20, 20] and flat["gap_days_median"] == 5


def test_runway_co2_matches_diesel_burned():
    r = R.runway(20000, 1000, 25, saving_frac=0.3)
    assert abs(r["co2_to_delivery_t"]["baseline"] - r["diesel_to_delivery_l"]["baseline"] * 2.70 / 1000) < 1e-9
    assert abs(r["diesel_to_delivery_l"]["baseline"] - 25000) < 120         # mean daily use is preserved (about 5 Monte-Carlo sigmas)
    assert r["diesel_to_delivery_l"]["with_saving"] == pytest.approx(0.7 * r["diesel_to_delivery_l"]["baseline"], rel=1e-9)


@pytest.mark.parametrize("kw", [dict(stock_l=0), dict(daily_l=-1), dict(delivery_day=0), dict(delivery_day=400), dict(cv=2), dict(saving_frac=0.95), dict(delay_days=99), dict(stock_l=float("nan"))])
def test_runway_validates_inputs(kw):
    with pytest.raises(ValueError): R.runway(**{"stock_l": 20000, "daily_l": 1000, "delivery_day": 25, **kw})


# ---------------------------------------------------------------- stress report
@pytest.mark.skipif(not (ROOT / "results/stress.json").exists(), reason="run `make stress` first")
def test_stress_report_all_gated_tests_pass_and_limits_are_disclosed():
    s = json.loads((ROOT / "results/stress.json").read_text())
    failed = [t["name"] for t in s["tests"] if t["passed"] is False]
    assert not failed, failed
    assert s["passed"] == s["total"] and any(t["group"] == "limits" for t in s["tests"])
