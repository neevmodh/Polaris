# Polaris

One website for the two Greenovators Track 3 projects: **SCOPE** (carbon accounting, ML gap-filler, abatement and fuel runway)
and **Task 3** (Sentinel-2 forest-loss and lake-water screening). It is a Next.js 16 app whose backend talks to both Python engines.

```
cd Polaris && ./run.sh        # then open http://localhost:3100
```

## Layout
```
Polaris/
  web/        Next.js app: pages, charts, API routes, browser tests
  engines/    sat_worker.py: a JSON-lines wrapper over Task3's `monitor` package (read-only use of Task3)
  tests/      end-to-end tests of that wrapper (8)
  data/       Polaris's own files: review notes, custom fetches, uploads, U-Net mask cache
../SCOPE      carbon engine, models and tests, used through carbon/api_worker.py (unchanged)
../Task3      satellite engine, models and cached scenes (unchanged except for its own fixes)
```
Paths are relative; override with `SCOPE_DIR`, `TASK3_DIR`, `SCOPE_PYTHON`, `TASK3_PYTHON`.

## Sheets
| No. | Sheet | Route |
|---|---|---|
| 00 | Overview with live readings | `/` |
| 01–03 | Calculator, ML estimator, scenario compare (+ printable report) | `/carbon/...` |
| 04–05 | Abatement planner, fuel runway | `/plan/...` |
| 06–07 | Forest loss, lake water | `/earth/forest`, `/earth/lake` |
| 08–10 | Carbon models, Earth models, method and sources | `/evidence/...` |

## Earth workspace (ported from the Streamlit app)
Case studies, custom-region fetch (background job with progress), GeoTIFF upload, swipe or side-by-side viewer with layers and a legend,
numbered region markers, a review queue with saved decisions, model evidence, scene provenance, and ZIP, GeoJSON, CSV and JSON export.
Not ported (still in the Streamlit app, `Task3/run.sh`): rectangle drawing on an OpenStreetMap basemap, the PNG/JPEG comparison studio,
the multi-date timeline, and the basemap-based geographic view.

## Tests
```
make test-sat      # 8 end-to-end tests of the satellite bridge, incl. the published case-study numbers
make test-carbon   # 53 carbon tests
make e2e           # 114 real-browser checks (site must be running; Chrome required)
```

## Honest status
The carbon ML models are trained on **synthetic** companies; the satellite scenes are **real**. Forest results are agreement with a
Hansen reference in one region, not field validation. Lake values are optical proxies, not concentrations. The link from mapped
forest loss to tonnes of CO₂ is not built. See the Method sheet in the app for sources and licences.
