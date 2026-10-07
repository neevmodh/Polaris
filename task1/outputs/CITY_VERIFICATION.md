# Noida & Ahmedabad verification — 8 October 2026

- 1,460 real daily CT2026 boundary-layer CO₂ estimates per city, 2022-01-01–2025-12-30; no missing source days.
- Eight native three-hourly values per day; source URL, retrieval time and native cell retained for each extract.
- City CSV SHA-256 checksums verified before loading; actual native cell bounds contain the requested city coordinates.
- 34 automated tests passed, including source extraction checks, chronological leakage protection, interval/export checks, city switching, model/horizon changes, all five tabs and upload mode. A targeted app regression check also passed after adding the benchmark warning.
- Browser uploaded the real Noida regional CSV through the file chooser, confirmed its trained forecast, and checked the supplied-coordinate marker. Uploaded data remain labeled unverified concentration data, not automatically certified sensor measurements.
- Browser verified actual SVG marker clicks for Ahmedabad and Noida, selected-city sidebar and forecast updates, zoom, pan, focus, reset, and the two-city comparison.
- Saved trained Ridge and random-forest models, 30-day forecasts, 35 model/horizon benchmark rows per city, held-out traces, source metadata, HTML report and analysis ZIP.

## 14-day chronological holdout

| City | Calibration-selected ML | MAE (ppm) | Persistence MAE (ppm) | Nominal 90% band coverage |
|---|---|---:|---:|---:|
| Noida | Random forest | 6.805 | 8.051 | 82.2% |
| Ahmedabad | Lag Ridge | 8.637 | 5.671 | 51.3% |

Noida's selected ML improves on persistence. Ahmedabad's ML underperforms this baseline and its nominal bands under-cover; a visible forecast warning reports this, and the baseline remains selectable. These metrics assess the regional modeled source, not independent city sensors. Forecasts are historical, starting 2025-12-31, not live October 2026 forecasts. Native India resolution is 3° × 2°; no neighborhood-level spatial accuracy is claimed.

Screenshots: city_map_preview.jpg and city_forecast_preview.jpg.
