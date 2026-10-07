"""The air bridge must serve Task 1's own trained results unchanged, and refuse bad input in words.

Run with task1's interpreter:  cd task1 && .venv/bin/python -m pytest -q ../Polaris/tests/test_air_worker.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TASK1 = Path(__file__).resolve().parents[2] / "task1"
WORKER = Path(__file__).resolve().parents[1] / "engines" / "air_worker.py"


@pytest.fixture(scope="module")
def worker():
    p = subprocess.Popen([sys.executable, str(WORKER)], cwd=TASK1, text=True,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         env={**os.environ, "TASK1_DIR": str(TASK1), "PYTHONDONTWRITEBYTECODE": "1"})
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


def test_both_cities_are_offered_with_their_provenance(worker):
    cities = ok(worker("meta"))["cities"]
    assert {c["station"] for c in cities} == {"NOIDA", "AHMEDABAD"}
    for c in cities:
        assert "CarbonTracker" in c["origin"]
        assert "not a city sensor" in c["scope"].lower() or "not a city sensor" in c["scope"]
        assert len(c["grid_bounds"]) == 4


def test_a_forecast_carries_its_own_verdict_against_the_benchmark(worker):
    r = ok(worker("forecast", {"city": "NOIDA", "horizon": 14}))
    assert r["unit"] == "ppm" and r["horizon"] == 14
    assert len(r["forecast"]) == 14 and len(r["history"]) == 180
    assert r["final"]["lower"] < r["final"]["value"] < r["final"]["upper"]
    # The app decides whether the model won, so the wording on the page can never drift from the numbers.
    assert r["beats_persistence"] == (r["mae"] < r["persistence_mae"])
    assert (r["skill_pct"] > 0) == r["beats_persistence"]
    assert {m["model"] for m in r["metrics"]} >= {"Persistence", "Random forest"}


def test_a_city_where_the_model_loses_still_reports_honestly(worker):
    """Ahmedabad is the awkward case: the trained model is worse than persistence and must say so."""
    r = ok(worker("forecast", {"city": "AHMEDABAD", "horizon": 14}))
    assert r["mae"] > r["persistence_mae"]
    assert r["beats_persistence"] is False
    assert r["skill_pct"] < 0


def test_alerts_are_bounded_and_counted(worker):
    loose = ok(worker("alerts", {"city": "NOIDA", "sigma": 1.5}))
    tight = ok(worker("alerts", {"city": "NOIDA", "sigma": 4.0}))
    assert loose["days"] == tight["days"] == 180
    assert loose["flagged"] >= tight["flagged"], "a lower threshold cannot flag fewer days"
    assert loose["flagged"] == sum(1 for r in loose["rows"] if r["flag"])


def test_bad_input_is_refused_in_plain_words(worker):
    for cmd, args, word in [("forecast", {"city": "ATLANTIS"}, "Unknown city"),
                            ("forecast", {"city": "NOIDA", "horizon": 999}, "horizon"),
                            ("alerts", {"city": "NOIDA", "sigma": 99}, "sigma")]:
        r = worker(cmd, args)
        assert not r["ok"] and r["kind"] == "input"
        assert word in r["error"]


def test_the_comparison_sheet_covers_every_city(worker):
    r = ok(worker("compare"))
    assert {c["station"] for c in r["cities"]} == {"NOIDA", "AHMEDABAD"}
    assert all(c["final"]["value"] > 0 for c in r["cities"])
