# Atmos — Machine learning greenhouse gas forecasts for Noida & Ahmedabad

A local Streamlit application that trains real Ridge regression and random-forest models to forecast **daily CO₂ levels for the regions containing Noida and Ahmedabad**. It also trains on uploaded local CO₂ or methane sensor CSVs.

```sh
cd /Users/neev/Downloads/POLARIS/task1
./run.sh
```

Open http://localhost:8501. The bundled city histories and offline map work without an API key or network connection after installation.

## Six features

1. **City-specific ML forecasts:** 7, 14 or 30 days; three trained ML models; two baseline comparisons; nominal 90% uncertainty bands; adjustable review level.
2. **Interactive city map and comparison:** city selection updates the forecast; zoom, pan, reset, focus; actual source grid footprints; side-by-side forecast and accuracy comparison.
3. **Model lab:** chronological train/calibration/test split, held-out predictions, MAE/RMSE, interval coverage, baseline skill, feature importance, trained model download and retraining.
4. **History and statistical alerts:** historical trends, monthly heatmap and unusually high values against a threshold calculated using preceding data only.
5. **Ask the analyst:** a Groq-hosted language model turns the figures on the page into plain
   English — what the forecast says, whether the model beat the benchmark, what the caveats are.
   It is handed the computed numbers only and told to quote them exactly and invent nothing;
   the app itself decides whether the model beat persistence, so the text cannot disagree.
6. **Local sensor input and exports:** daily CO₂ (ppm) or CH₄ (ppb) CSV upload, sensor coordinates, forecast CSV, portable HTML report, full analysis ZIP with source metadata and checksums.

## What the included data represent

**These are genuine NOAA CarbonTracker CT2026 regional model estimates, not readings from sensors in either city.** The native global grid is **3° longitude × 2° latitude**. It cannot resolve neighborhoods or isolate city emissions. Accuracy is evaluated against this regional source, not independent city sensors.

The variable `pbl_co2` is the dry-air CO₂ mole fraction pressure-averaged through the planetary boundary layer, in micromol/mol (ppm). A daily UTC value averages the eight three-hourly values in the nearest native cell. Nothing is spatially interpolated or adjusted to invent city differences.

| Location | Coordinates used | Source cell center | Cell footprint |
|---|---|---|---|
| Noida | 28.5355° N, 77.3910° E | 29° N, 76.5° E | 28–30° N, 75–78° E |
| Ahmedabad | 23.0225° N, 72.5714° E | 23° N, 73.5° E | 22–24° N, 72–75° E |

The download targets 2022-01-01 through 2025-12-30. Read `data/cities/manifest.json` for the actual included dates and missing-file counts. **Forecasts begin after the last available history date, not today.** They are historical research forecasts, not live monitoring. No AQI, NO₂, carbon monoxide or emission mass is substituted for greenhouse-gas concentration.

Three-hourly extracted values, source URLs and retrieval times are retained in `data/cities/raw/*.json`; daily CSVs have SHA-256 checksums. Downloads use HTTP byte ranges to read the small boundary-layer array from public NetCDF files rather than downloading each complete global atmosphere file.

```sh
.venv/bin/python scripts/fetch_cities.py
.venv/bin/python scripts/train.py --all --horizon 14
.venv/bin/python -m pytest -q
```

Downloads are resumable. Refresh the app with **Reload city data** after regenerating an extraction. Forecast artifacts live in `outputs/co2_noida` and `outputs/co2_ahmedabad`. `models.joblib` contains fitted models and reproducibility metadata; only load joblib files from trusted sources.

## The AI analyst

```sh
cp .env.example .env     # then paste your own key
# GROQ_API_KEY=gsk_...
# GROQ_MODEL=openai/gpt-oss-120b
```

Without a key the tab explains how to enable itself rather than failing. Answers are cached per
question and per set of figures, so re-asking costs nothing. Nothing but the figures shown in the
"Exactly what the model was shown" panel is sent: no raw data file, no key, no personal
information. `.env` is git-ignored — rotate any key that has been shared.

The generated text is an explanation, not a result. The Model lab tab remains the source of truth.

## Modeling

Seasonal Ridge models trend and annual harmonics. Lag Ridge and random forest predict residual variation using past concentration lags, rolling statistics and forecast horizon. Automatic choice minimizes calibration RMSE among these three trained ML models. Persistence and seasonal persistence remain benchmarks, including when they outperform ML.

The calendar split is 72% training / 14% calibration / 14% test. Labels crossing split boundaries are purged. Rolling-origin test predictions use frozen training models and only history available at each origin. Targets are never imputed. Missing feature inputs permit up to three days of causal forward fill. Nominal 90% bands use calibration absolute errors by horizon; the next longer tested horizon supplies intermediate-day widths. Dependence, drift and production refitting can change coverage; actual holdout coverage is shown.

Production models are refit after evaluation. The model consumes concentration history, not future weather, traffic or source inventories. Statistical flags and user review levels are analytical tools, not health or regulatory limits or evidence of an emission source.

## Local sensor data

CSV columns: `date,value`, optionally `unit`. One positive finite daily UTC mean per date; at least 900 observed days spanning three years and sufficiently complete recent history for lag features. Choose the correct gas; CO₂ uses ppm, CH₄ uses ppb. Missing sentinels, duplicates, wrong units and future dates are rejected. Your CSV stays in the local application. Calibration and geographic representativeness are the provider's responsibility. Downloaded regional examples remain labeled regional estimates.

For finer regional modeled data, [CAMS greenhouse gas forecasts](https://ads.atmosphere.copernicus.eu/datasets/cams-global-greenhouse-gas-forecasts?tab=overview) provide CO₂ and CH₄ on a 0.1° output grid. Downloading requires a Copernicus account and accepted license terms. That data is **not bundled**, and the app does not claim NOAA has CAMS resolution.

## Tests

```sh
.venv/bin/python -m pytest -q tests
```

39 tests covering the data loaders, the chronological split, the forecasts and baselines, the map,
the dashboard itself, and the analyst — that it fails readably without a key or network and that
the API key never reaches the prompt.

## Sources and GitHub references

- [NOAA CarbonTracker CT2026](https://gml.noaa.gov/ccgg/carbontracker/CT2026/), Jacobson et al. (2026), [DOI 10.25925/hqp0-rk68](https://doi.org/10.25925/hqp0-rk68). [Source NetCDF archive](https://gml.noaa.gov/aftp/products/carbontracker/co2/CT2026/molefractions/co2_total/).
- [Usage policy](https://gml.noaa.gov/ccgg/carbontracker/CT2026/citation.php): unrestricted non-commercial use with attribution. Retain the policy when reusing the dataset. CarbonTracker CT2026 results provided by NOAA GML, Boulder, Colorado, USA from carbontracker.noaa.gov.
- [scikit-learn](https://github.com/scikit-learn/scikit-learn), BSD-3-Clause: actual model implementation dependency.
- [MGGTSP-CAT](https://github.com/Changbin-Z/MGGTSP-CAT): localized methane forecasting research reference; no unlicensed code copied.
- [Stanford methane-gapfill-ml](https://github.com/stanfordmlgroup/methane-gapfill-ml), Apache-2.0: attributed reference snapshot; methane flux gap filling is distinct from future concentration forecasting.
- [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/), public-domain offline country boundaries. Source and checksum retained in `assets/map_provenance.json`.

Earlier NOAA baseline station files and their tests are retained for forecasting regression checks; the dashboard's default data and geography now target the two requested city regions.
