# NetZeroAI — Microgrid Solar/Wind Distribution Optimizer

End-to-end implementation for TRACK 3 / Area 2: forecast renewable generation and load, then optimize microgrid dispatch for cost, carbon, battery health and resilience.

## Architecture

Weather + historical generation/load → XGBoost forecasts → 24h dispatch optimization (Pyomo + HiGHS) → battery/grid/renewables → KPIs + scenarios.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m src.data.generate_demo_data
python -m src.forecasting.train_all
python -m src.optimization.demo
uvicorn api.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the API. The Next.js dashboard in `frontend/` can be run with Node 20+.

## Real data

```bash
python -m src.data.download_pvgis
python -m src.data.download_openmeteo
python -m src.data.download_uci
python -m src.data.clean_and_merge
python -m src.forecasting.train_all
```

If external downloads are unavailable, the demo generator creates a realistic synthetic dataset so the full pipeline remains executable.

## The AI analyst

The dashboard can explain its own plan in plain words. A Groq-hosted language model is given
**only the numbers the optimiser produced** — KPIs, dispatch totals, battery state of charge,
the plan type and the configured limits — and is told to quote them exactly and invent nothing.
It never computes a figure, and the planner stays the source of truth.

```bash
cp .env.example .env        # then paste your own key
# GROQ_API_KEY=gsk_...
# GROQ_MODEL=openai/gpt-oss-120b
```

`GET /ask/status` reports whether a key is present; without one the dashboard hides the feature
instead of failing. `.env` is git-ignored — rotate any key that has been shared.

## Main API
- `GET /health` — data and model availability
- `GET /forecast` — next 24 h of solar, wind and load
- `GET /metrics` — held-out forecast error against a naive baseline
- `POST /optimize` — optimal dispatch plus KPIs
- `POST /simulate` — the same, summarised
- `POST /scenario/{name}` — re-plan the day under a disturbance
- `POST /ask` — plain-language explanation of a computed plan

Scenario names: `cloud_event`, `wind_drop`, `load_spike`, `battery_low`, `grid_outage`.

Every dispatch response carries `method`: `optimised` when HiGHS solved it, or
`rule-based fallback` with a `fallback_reason` when it could not. The dashboard labels the
chart accordingly, so a fallback plan is never presented as an optimal one.

## What the numbers mean, and do not mean

- The bundled dataset is **synthetic demo data**. The forecast errors show that the pipeline
  works; they are not field accuracy.
- `renewable_utilization_pct` is energy used divided by energy *offered* by sun and wind, so
  spilling generation lowers it. `renewable_spilled_kwh` reports the difference.
- `unserved_kwh` is load the microgrid could not meet. Under `grid_outage` it is non-zero by
  design: the honest answer is that a day-long outage sheds load.
- The analyst's text is generated. Treat it as a reading of the KPIs, not as a finding.

## Tests

```bash
.venv/bin/python -m pytest -q tests
```

Covers the energy balance in both planners, every scenario, the fallback labelling, the
forecast merge, and that the analyst fails readably and never receives the API key.
