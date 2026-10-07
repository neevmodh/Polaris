# POLARIS · Greenovators Hackathon 2026 · Track 3 · Team CarbonIQ

One website over four tested Python engines. Measure what a site emits, track what is already in
the air above a city, see what changed on the ground from orbit, and plan the cuts — then ask an
analyst to explain any sheet in plain words.

```
POLARIS/
├── Polaris/      the website: Next.js app + the bridge to all four engines      ← start here
├── SCOPE/        carbon engine: footprint, ML gap-filler, abatement, dispatch, fuel runway
├── task1/        air engine: regional CO₂ histories and trained forecasts (Atmos)
├── Task3/        satellite engine: forest-loss and lake screening
├── netzero-ai/   microgrid engine: solar + wind + battery dispatch optimiser
├── docs/         hackathon brochure, schedule, poster and the proposal PDFs
├── run.sh        starts the website
└── README.md
```

## Run

```
./run.sh                 # builds if needed, serves http://localhost:3100
```

First time only: `cd Polaris && make install`. The four Python environments
(`SCOPE/.venv`, `task1/.venv`, `Task3/.venv`, `netzero-ai/.venv`) already exist.

The analyst needs a Groq key. Copy `.env.example` to `.env` beside this file and paste one in:

```
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b
```

Without a key every sheet still works; the analyst panel explains how to switch itself on.
`.env` is git-ignored — rotate any key that has been shared.

## The sheets

| Section | Sheets | Engine |
|---|---|---|
| Carbon | 01 Calculator · 02 Estimator · 03 Compare · Report | `SCOPE` |
| Air | 04 Air forecast · 05 Air alerts | `task1` |
| Plan | 06 Abatement · 07 Dispatch · 08 Microgrid · 09 Fuel runway | `SCOPE`, `netzero-ai` |
| Earth | 10 Forest loss · 11 Lake water | `Task3` |
| Evidence | 12 Carbon models · 13 Earth models · 14 Method | all |

Each engine runs as a long-lived child process speaking JSON lines, in its own virtual
environment, with its own project as the working directory — so the website reuses the tested code
rather than reimplementing any formula. See `Polaris/web/lib/py.ts` and `Polaris/engines/`.

## The analyst

A Groq-hosted language model is handed the figures a sheet has **already computed** and asked to
put them into words. It never produces a number. Where a judgement could drift from the data, the
app computes the judgement itself and passes it down as a `VERDICT` line the model may not
contradict — for example whether a forecast actually beat its benchmark. Every sheet shows the
exact text that was sent.

## Test

```
cd Polaris && make test     # 8 satellite + 6 air + 7 microgrid bridge tests, 72 carbon tests, 142 browser checks
cd Task3   && .venv/bin/python -m pytest -q      # 68 satellite tests
cd task1   && .venv/bin/python -m pytest -q      # 39 air tests
cd netzero-ai && .venv/bin/python -m pytest -q   # 18 microgrid tests
```

The browser checks need the site running on :3100 and Chrome.

## What this repository does not carry

Three kinds of file are left out, so clone and rebuild them once:

| Missing | Rebuild with | Why |
|---|---|---|
| `Task3/models/water_unet.pth` | `cd Task3 && .venv/bin/python scripts/setup_water_model.py` | 118 MB, past GitHub's hard file limit |
| `SCOPE/models/dispatch/*.joblib` | `cd SCOPE && .venv/bin/python -m carbon.dispatch_eval polar community` | 12 MB of regenerable forecasters |
| `task1/outputs/**/models.joblib` | nothing — the app trains and caches them on first run | runtime cache |
| `*/references/` | the READMEs link to each upstream project | vendored third-party checkouts |

The small models that make the site work immediately — the carbon gap-filler and the forest
random forest — are included. The four `.venv` directories and `node_modules` are not: see **Run**.

## What the numbers mean, and do not mean

- **Carbon ML is trained on synthetic data.** The footprint arithmetic and factors are real; the
  gap-filling model is a demonstration of the pipeline, not a validated predictor.
- **Air data is real** NOAA CarbonTracker CT2026, but it is a regional 3°×2° model estimate, not a
  city sensor. On Ahmedabad the trained model *loses* to persistence, and the sheet says so.
- **Satellite results are screening**, not proof of deforestation or pollution.
- **The microgrid dataset is synthetic demo data.** Its forecast errors show the pipeline works;
  they are not field accuracy.
- Spend-based Scope 3 is an industry-average estimate, never a measurement of a supplier.

Each sheet states its own provenance in the title block, and the *Method* sheet collects every
source, licence and limit.

## Running a piece on its own

Each engine is still a standalone project with its own app and tests:

- `cd Task3 && bash run.sh` — satellite Streamlit app on :8503 (has map drawing, an RGB studio and
  a multi-date timeline that are not yet surfaced in the website).
- `cd task1 && ./run.sh` — Atmos Streamlit app on :8501.
- `cd netzero-ai && ./run_demo.sh` — FastAPI on :8000, with its own dashboard in `frontend/`.
