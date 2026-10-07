"""Every disturbance must still produce a usable plan, and a plan that is not optimal must say so."""
import pandas as pd
import pytest
import yaml
from src.optimization.model import greedy_dispatch, kpis, optimize_dispatch
from src.simulation.scenarios import SCENARIOS, apply_scenario, run_scenario

CFG = yaml.safe_load(open('configs/config.yaml'))


@pytest.fixture
def day():
    return pd.read_csv('data/processed/master_hourly.csv', parse_dates=['timestamp']).tail(24).reset_index(drop=True)


@pytest.mark.parametrize('name', SCENARIOS)
def test_every_scenario_returns_a_full_day_plan(day, name):
    r = run_scenario(day, CFG, name)
    assert len(r['dispatch']) == len(day)
    assert r['method'] in ('optimised', 'rule-based fallback')
    assert r['kpis']['critical_load_coverage_pct'] <= 100 + 1e-9


def test_unknown_scenario_is_rejected(day):
    with pytest.raises(ValueError):
        apply_scenario(day, 'meteor_strike')


def test_an_outage_is_planned_not_abandoned(day):
    """Losing the grid must still give an optimal plan that shows the shortfall, not an error."""
    r = run_scenario(day, CFG, 'grid_outage')
    assert r['method'] == 'optimised'
    assert r['kpis']['grid_import_kwh'] == pytest.approx(0, abs=1e-6)
    assert r['kpis']['unserved_kwh'] > 0, 'an outage this size cannot be fully served; that must be visible'
    assert r['kpis']['critical_load_coverage_pct'] < 100


def test_the_optimiser_beats_the_rule_of_thumb_under_outage(day):
    x = apply_scenario(day, 'grid_outage')
    c = {**CFG, 'grid': {**CFG['grid'], 'import_kw': 0, 'export_kw': 0}}
    assert kpis(x, optimize_dispatch(x, c))['unserved_kwh'] < kpis(x, greedy_dispatch(x, c))['unserved_kwh']


def test_a_fallback_plan_labels_itself(day):
    d = greedy_dispatch(day, CFG)
    assert d.attrs['method'] == 'rule-based fallback'
    assert d.attrs['fallback_reason']
    assert optimize_dispatch(day, CFG).attrs['method'] == 'optimised'


def test_an_ordinary_day_is_actually_optimised(day):
    r = run_scenario(day, CFG, 'cloud_event')
    assert r['method'] == 'optimised'
    assert r['fallback_reason'] is None


@pytest.mark.parametrize('plan', ('optimised', 'rule-based'))
def test_energy_balance_holds_in_both_kinds_of_plan(day, plan):
    x = apply_scenario(day, 'grid_outage')
    c = {**CFG, 'grid': {**CFG['grid'], 'import_kw': 0, 'export_kw': 0}}
    d = optimize_dispatch(x, c) if plan == 'optimised' else greedy_dispatch(x, c)
    lhs = d.solar_kw + d.wind_kw + d.grid_import_kw + d.discharge_kw + d.unserved_kw
    rhs = x.load_kw.reset_index(drop=True) + d.charge_kw + d.grid_export_kw
    assert (abs(lhs - rhs) < 1e-5).all()
    assert d.soc.between(CFG['battery']['soc_min'] - 1e-6, CFG['battery']['soc_max'] + 1e-6).all()
    # Spilled renewable energy is reported, never hidden inside the balance.
    spilled = (x.solar_available_kw + x.wind_available_kw).reset_index(drop=True) - d.solar_kw - d.wind_kw
    assert (abs(d.curtail_kw - spilled) < 1e-5).all()


def test_renewable_utilisation_counts_what_was_offered_not_what_was_taken(day):
    """A plan that spills sun and wind must not still report 100% utilisation."""
    x = apply_scenario(day, 'grid_outage')
    c = {**CFG, 'grid': {**CFG['grid'], 'import_kw': 0, 'export_kw': 0}}
    k = kpis(x, optimize_dispatch(x, c))
    assert k['renewable_spilled_kwh'] > 0
    assert k['renewable_utilization_pct'] < 100
    assert k['renewable_used_kwh'] + k['renewable_spilled_kwh'] == pytest.approx(k['renewable_offered_kwh'], rel=1e-6)
