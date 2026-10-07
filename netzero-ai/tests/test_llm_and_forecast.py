"""The analyst must stay an explainer: it never computes a number, and it fails readably."""
import pandas as pd
import pytest
from src import llm
from src.forecasting.predict import MODEL_MAP, forecast_all


def test_each_signal_gets_its_own_forecast(monkeypatch):
    """Merging the three models once produced duplicate columns and an empty dashboard."""
    hist = pd.DataFrame({'timestamp': pd.date_range('2025-01-01', periods=200, freq='h'),
                         'solar_available_kw': range(200), 'wind_available_kw': [5] * 200, 'load_kw': [300] * 200})
    seen = []

    def fake(kind, history, horizon=24):
        seen.append(kind)
        out = pd.DataFrame({'timestamp': pd.date_range('2025-01-09 08:00', periods=horizon, freq='h')})
        for c in MODEL_MAP.values():
            out[c] = {'solar': 1.0, 'wind': 2.0, 'load': 3.0}[kind]      # each model claims every column
        return out

    monkeypatch.setattr('src.forecasting.predict.forecast', fake)
    out = forecast_all(hist, 24)
    assert seen == ['solar', 'wind', 'load']
    assert len(out) == 24
    assert list(out.columns) == ['timestamp', 'solar_available_kw', 'wind_available_kw', 'load_kw']
    # Each column must come from its own model, not from whichever merged first.
    assert out.solar_available_kw.eq(1.0).all()
    assert out.wind_available_kw.eq(2.0).all()
    assert out.load_kw.eq(3.0).all()


def test_a_missing_key_is_a_readable_message_not_a_crash(monkeypatch):
    monkeypatch.setattr(llm, '_env', lambda name, default='': '')
    assert not llm.available()
    with pytest.raises(RuntimeError, match='GROQ_API_KEY'):
        llm.ask('Why?', 'data', 'system')


def test_an_api_failure_is_reported_in_words(monkeypatch):
    class Resp:
        status_code = 429
        def json(self): return {'error': {'message': 'Rate limit reached'}}
    monkeypatch.setattr(llm, '_env', lambda name, default='': 'key' if name == 'GROQ_API_KEY' else default)
    monkeypatch.setattr(llm.requests, 'post', lambda *a, **k: Resp())
    with pytest.raises(RuntimeError, match='Rate limit reached'):
        llm.ask('Why?', 'data', 'system')


def test_the_question_and_the_computed_data_both_reach_the_model(monkeypatch):
    sent = {}

    class Resp:
        status_code = 200
        def json(self): return {'choices': [{'message': {'content': 'Because the battery was full.'}}]}

    def capture(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return Resp()

    monkeypatch.setattr(llm, '_env', lambda name, default='': 'key' if name == 'GROQ_API_KEY' else (default or 'm'))
    monkeypatch.setattr(llm.requests, 'post', capture)
    answer = llm.ask('Why no grid import?', 'grid_import_kwh: 0', 'You explain dispatch.')
    assert answer == 'Because the battery was full.'
    user = sent['messages'][1]['content']
    assert 'grid_import_kwh: 0' in user and 'Why no grid import?' in user
    assert sent['messages'][0]['role'] == 'system'
    assert sent['temperature'] <= 0.3, 'explanations of fixed numbers should not be creative'
