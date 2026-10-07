"""Groq chat helper (OpenAI-compatible endpoint). The key is read from GROQ_API_KEY or a local .env file and never leaves the server."""
import os, requests
from pathlib import Path

URL = "https://api.groq.com/openai/v1/chat/completions"


def _env(name, default=""):
    if os.environ.get(name): return os.environ[name]
    f = Path(__file__).resolve().parent
    for p in (f / ".env", f.parent / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith(name + "="): return line.split("=", 1)[1].strip()
    return default


def available(): return bool(_env("GROQ_API_KEY"))


def model_name(): return _env("GROQ_MODEL", "openai/gpt-oss-120b")


def ask(question, context, system, max_tokens=700):
    """Answer `question` using only `context` (numbers computed by the app). Raises RuntimeError with a readable message."""
    key = _env("GROQ_API_KEY")
    if not key: raise RuntimeError("No GROQ_API_KEY set. Add it to the .env file.")
    body = {"model": _env("GROQ_MODEL", "openai/gpt-oss-120b"), "max_tokens": max_tokens, "temperature": 0.2,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": f"APP DATA (authoritative):\n{context}\n\nQUESTION: {question}"}]}
    try:
        r = requests.post(URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=45)
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach Groq: {e.__class__.__name__}") from e
    if r.status_code != 200:
        try: msg = r.json()["error"]["message"]
        except Exception: msg = r.text[:120]
        raise RuntimeError(f"Groq error {r.status_code}: {msg}")
    return (r.json()["choices"][0]["message"].get("content") or "").strip()
