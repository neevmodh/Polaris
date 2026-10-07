"""The microgrid bridge must label every plan honestly and keep the energy balance it reports.

Run with netzero-ai's interpreter:  cd netzero-ai && .venv/bin/python -m pytest -q ../Polaris/tests/test_grid_worker.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GRID = Path(__file__).resolve().parents[2] / "netzero-ai"
WORKER = Path(__file__).resolve().parents[1] / "engines" / "grid_worker.py"


@pytest.fixture(scope="module")
def worker():
    p = subprocess.Popen([sys.executable, str(WORKER)], cwd=GRID, text=True,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         env={**os.environ, "NETZERO_DIR": str(GRID), "PYTHONDONTWRITEBYTECODE": "1"})
    assert json.loads(p.stdout.readline())["ready"]

    def call(cmd, args=None):
        p.stdin.write(json.dumps({"id": 1, "cmd": cmd, "args": args or {}}) + "\n")
        p.stdin.flush()
        return json.loads(p.stdout.readline())

    yield call
    p.terminate()


def ok(reply):
    assert reply["ok"], reply.get("error")
    return reply["result"]


def test_the_plant_and_every_scenario_are_described(worker):
    m = ok(worker("meta"))
    assert set(m["scenarios"]) == {"cloud_event", "wind_drop", "load_spike", "battery_low", "grid_outage"}
    assert m["config"]["battery"]["capacity_kwh"] > 0
    assert m["data_ready"]


def test_an_ordinary_day_is_optimised_and_fully_served(worker):
    r = ok(worker("plan"))
    assert r["method"] == "optimised" and r["fallback_reason"] is None
    assert len(r["dispatch"]) == 24 and len(r["forecast"]) == 24
    assert r["kpis"]["unserved_kwh"] == pytest.approx(0, abs=1e-6)
    assert all(20 - 1e-6 <= h["soc_pct"] <= 90 + 1e-6 for h in r["dispatch"])


def test_the_hourly_plan_balances_against_the_demand_it_was_given(worker):
    r = ok(worker("plan"))
    for h, f in zip(r["dispatch"], r["forecast"]):
        supply = h["solar_kw"] + h["wind_kw"] + h["grid_import_kw"] + h["discharge_kw"] + h["unserved_kw"]
        assert supply == pytest.approx(f["load_kw"] + h["charge_kw"], abs=1e-4)


def test_losing_the_grid_sheds_load_and_says_so(worker):
    r = ok(worker("plan", {"scenario": "grid_outage"}))
    assert r["kpis"]["grid_import_kwh"] == pytest.approx(0, abs=1e-6)
    assert r["kpis"]["unserved_kwh"] > 0, "an outage this size cannot be fully served; that must be visible"
    assert r["kpis"]["critical_load_coverage_pct"] < 100


def test_renewable_utilisation_is_measured_against_what_was_offered(worker):
    k = ok(worker("plan"))["kpis"]
    assert k["renewable_used_kwh"] + k["renewable_spilled_kwh"] == pytest.approx(k["renewable_offered_kwh"], rel=1e-6)
    assert 0 <= k["renewable_utilization_pct"] <= 100 + 1e-9


def test_the_comparison_covers_the_ordinary_day_and_all_five_disturbances(worker):
    rows = ok(worker("compare"))["rows"]
    assert [r["scenario"] for r in rows][0] == "normal"
    assert len(rows) == 6
    assert all(r["method"] in ("optimised", "rule-based fallback") for r in rows)
    outage = next(r for r in rows if r["scenario"] == "grid_outage")
    assert outage["kpis"]["unserved_kwh"] > 0


def test_bad_input_is_refused_in_plain_words(worker):
    for args, word in [({"scenario": "meteor_strike"}, "Unknown scenario"), ({"hours": 500}, "hours")]:
        r = worker("plan", args)
        assert not r["ok"] and r["kind"] == "input"
        assert word in r["error"]
