# Carbon Footprint Estimator (Scope 1/2/3) — Team CarbonIQ, Track 3

Part of **Polaris**. The Polaris diesel saving is entered as a percentage today (default 26.8%, illustrative); it is not yet linked to a Polaris simulation run.

## DATA STATUS (read first)
The ML models are currently trained on **SYNTHETIC** company data (`carbon/data_synth.py`, illustrative intensities),
because the real BRSR dataset was not available. All reported ML metrics demonstrate the pipeline only.
Swap in real data: `python -m carbon.explore <brsr.csv>` → adjust `classify()` → `python -m carbon.prepare_brsr <brsr.csv>` → `make train`.
`prepare_brsr.py` is untested against the real file.

## Web app
The website now lives in the merged project, `../Polaris` (Next.js, same Python engine, plus the satellite sheets). Start it with `../Polaris/run.sh`.
This folder keeps the carbon engine (`carbon/`), its data, models, results, tests and the original Streamlit dashboard (`app.py`).

## Audit log (gaps found and fixed)
| Problem found | Fix |
|---|---|
| Abatement double count: solar 400k + PPA 50% on 500k kWh claimed 439 t against a 337 t Scope 2 | PPA applies only to grid kWh left after solar; solar capped at grid draw (test added) |
| Real BRSR has no employees / renewable share; all-NaN columns were silently dropped by sklearn, which would break SHAP and feature names | `usable_numeric()` drops unusable features up front and stores the list in the model (test trains on all-NaN features) |
| No overfitting check | Train vs CV vs test RMSE and an `overfit_ratio` flag. RandomForest is flagged (1.7-1.8x) on both targets |
| Single split, no uncertainty on the headline claim | Company-bootstrap 95% CI on improvement vs the baseline, plus an out-of-time check (train <=2023, score 2024+, disjoint companies) |
| Intervals ignored heteroscedasticity | Adaptive (normalised) conformal vs Mondrian conformal, chosen on a held-out half of the calibration companies |
| Scope 2 used a generation-side factor without saying so | Optional T&D-loss gross-up (default 0 = published CEA figure); market-based Scope 2 not covered |
| Tab 3 baseline was disconnected from tab 1 | Tab 3 now uses tab 1's inputs and Monte-Carlo Scope 3 |
| Silent bad inputs / extrapolation | Unknown fuel raises; predictions warn on unseen sector, turnover out of range, or year beyond training data |
| Weak test (steel factor within 1.0) / unpinned dependencies | Exact USEEIO value asserted; `requirements.txt` pinned |

## QA round 2 (`tests/test_qa.py`, 34 tests total)
Found and fixed: negative/NaN/infinite inputs were silently accepted; lever fractions above 1 claimed more abatement than the baseline;
`macc([])` crashed the dashboard when all inputs were zero; `adoption_years=0` divided by zero; zero turnover crashed prediction while
negative or NaN turnover silently returned garbage; years before the training range gave no warning; the BRSR adapter misfiled the combined
Scope 1+2 intensity and mislabelled rupees as crore. Verified: no company shared between splits, shuffled-label negative control loses all
skill, a fresh synthetic world (new seed) gives RMSE well below baseline with 90-94% interval coverage, training is bit-for-bit reproducible,
property tests (hypothesis) on linearity, ordering and abatement caps, and fuzzing of the dashboard. Eight deliberately injected bugs were all caught by the suite.

## Final round: model testing
`carbon/stress.py` scores the shipped models on 3,000 fresh companies (15,301 company-years) they never saw: error vs baseline, coverage overall and by sector, size and year,
sensitivity to a +-10% input change, missing inputs, row order, and a learning curve. It found one real failure (Scope 1 coverage 79% in Pharmaceuticals).
The fix was cross-conformal calibration (out-of-fold residuals over train and calibration companies, then a refit on all of them): coverage is now 90.0% on both targets, worst sector 86%, 18 of 18 gated tests pass.
Three "limit" tests are reported on purpose, not hidden: a +50% regime shift, one sector doubling, and 1% unit-error labels all break the intervals, because the model cannot see a shift it was not trained on.
Rendering found a real bug too: a shared-link effect re-ran on every render (React error 185); store actions are now stable. Mutation testing of the new code: 8 of 8 injected bugs caught
(a first pass missed 3, which exposed weak tests that were then tightened).

## Known limitations (still open)
- **Synthetic data**: ridge wins because the generated emissions are close to log-linear in the features, so tree models cannot show their advantage. Do not read this as a finding about real companies.
- **Per-sector coverage varies** (about 0.70-0.90). Overall coverage is near 90%, but intervals are not valid per sector. Rows from one company are correlated, which shrinks the effective calibration sample.
- **Intervals are wide** (median upper/lower ratio about 5.6-6.4x) because company-level variation is large.
- Fuel factors are CO2 only; non-diesel fuel factors are approximate. Scope 3 uses US factors for Indian spend (+-50% sigma).
- No real-world validation until BRSR or facility data is used.

## What is real vs assumed
| Part | Source | Status |
|---|---|---|
| Scope 2 grid factor 0.675 tCO2/MWh | CEA CO2 Baseline Database v22.0, FY2025-26 | real |
| Diesel 2.70 kg/L | EPA (10.21 kg/gal) | real; other fuels approximate, verify |
| Scope 3 factors | EPA USEEIO v1.3 (downloaded, 1016 sectors) | real data, US factors applied to Indian spend (approximate, sigma 0.5) |
| Scope 1/2 ML gap-filler | trained on synthetic data | **synthetic** |
| Abatement costs / efficacies / grid decline | parameters in `abatement.py` | illustrative assumptions |

## Architecture
1. **Calculator** (`calculator.py`, `scope3.py`): activity data x factors, with Monte-Carlo propagation of factor uncertainty (P5-P95).
2. **ML gap-filler** (`train.py`): for sites without metered data. Four models (Ridge, RandomForest, XGBoost, LightGBM), tuned with
   company-grouped CV, best chosen by CV RMSE (method after Pladifes CGEE; code written independently), compared to a sector-median baseline.
   **Mondrian split-conformal** intervals (per sector) give 90% prediction bands. SHAP for explainability. Split by company: no leakage.
3. **Abatement** (`abatement.py`): levers (Polaris dispatch, solar, green PPA, supplier engagement), MACC, and a 2026-2050 Monte-Carlo pathway vs an SBTi 1.5C line.
4. **Dashboard** (`app.py`): Streamlit, 4 tabs.

Scope 3 is deliberately **not** ML-estimated: reported Scope 3 data is sparse and published ML accuracy is poor.

## Run
```
make setup && make all     # data (synthetic) -> train -> sample inference -> tests
make app
```
Outputs: `models/`, `results/` (metrics.json, model_comparison.csv, plots), `outputs/sample_inference.csv`.

## References
Nguyen et al. 2021 (Energy Economics); Nguyen et al. 2022 (Scope 3 data quality & ML accuracy); Assael et al. 2023 (arXiv 2212.10844);
Pladifes CGEE repository (method inspiration only; no code copied, no license file in that repo).
