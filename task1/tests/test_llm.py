"""The analyst explains the app's numbers; it must never be the thing that produces them."""
import pytest
from src import llm


def test_a_missing_key_is_a_readable_message_not_a_crash(monkeypatch):
    monkeypatch.setattr(llm, '_env', lambda name, default='': '')
    assert not llm.available()
    with pytest.raises(RuntimeError, match='GROQ_API_KEY'):
        llm.ask('Why?', 'data', 'system')


def test_an_api_failure_is_reported_in_words(monkeypatch):
    class Resp:
        status_code = 503
        def json(self): return {'error': {'message': 'Service unavailable'}}
    monkeypatch.setattr(llm, '_env', lambda name, default='': 'key' if name == 'GROQ_API_KEY' else default)
    monkeypatch.setattr(llm.requests, 'post', lambda *a, **k: Resp())
    with pytest.raises(RuntimeError, match='Service unavailable'):
        llm.ask('Why?', 'data', 'system')


def test_an_unreachable_host_does_not_leak_a_stack_trace(monkeypatch):
    def boom(*a, **k): raise llm.requests.RequestException('dns')
    monkeypatch.setattr(llm, '_env', lambda name, default='': 'key' if name == 'GROQ_API_KEY' else default)
    monkeypatch.setattr(llm.requests, 'post', boom)
    with pytest.raises(RuntimeError, match='Could not reach Groq'):
        llm.ask('Why?', 'data', 'system')


def test_the_figures_and_the_question_both_reach_the_model(monkeypatch):
    sent = {}

    class Resp:
        status_code = 200
        def json(self): return {'choices': [{'message': {'content': 'The forecast falls slightly.'}}]}

    def capture(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return Resp()

    monkeypatch.setattr(llm, '_env', lambda name, default='': 'key' if name == 'GROQ_API_KEY' else (default or 'm'))
    monkeypatch.setattr(llm.requests, 'post', capture)
    answer = llm.ask('What happens next?', 'Day-14 forecast: 446.82 ppm', 'You explain forecasts.')
    assert answer == 'The forecast falls slightly.'
    system, user = sent['messages']
    assert system['role'] == 'system' and 'You explain forecasts.' == system['content']
    assert '446.82 ppm' in user['content'] and 'What happens next?' in user['content']
    assert sent['temperature'] <= 0.3, 'explanations of fixed numbers should not be creative'


def test_the_api_key_is_never_part_of_the_prompt(monkeypatch):
    sent = {}

    class Resp:
        status_code = 200
        def json(self): return {'choices': [{'message': {'content': 'ok'}}]}

    def capture(url, headers=None, json=None, timeout=None):
        sent.update(prompt=str(json), auth=headers['Authorization'])
        return Resp()

    monkeypatch.setattr(llm, '_env', lambda name, default='': 'secret-key' if name == 'GROQ_API_KEY' else (default or 'm'))
    monkeypatch.setattr(llm.requests, 'post', capture)
    llm.ask('Why?', 'some figures', 'system')
    assert 'secret-key' not in sent['prompt']
    assert sent['auth'] == 'Bearer secret-key'
