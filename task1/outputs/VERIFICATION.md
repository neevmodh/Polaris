# Dashboard repair verification · 7 October 2026

## Fixed

- Replaced the display-only Folium iframe with a bidirectional local SVG map using bundled Natural Earth geometry. The map does not depend on tile servers, map CDNs or API keys.
- Map markers and accessible station buttons select the same NOAA station as the sidebar. Marker hit areas cover both the dot and its label; keyboard selection is supported.
- Zoom in/out, drag-to-pan, world reset and selected-site focus work. The equirectangular projection renders the South Pole without Mercator clipping.
- Map navigation can open the selected station's forecast tab.
- CSV uploads can include a manually specified station location. Coordinates appear in map details and exported provenance. Reference station buttons remain available when two datasets share a location.
- Forecast model/horizon controls reuse the trained 30-day result instead of retraining every model. Each selected model keeps its own calibrated interval widths.
- Added a local-data cache reload button and state-tracked tabs.

## Checks performed

- **29 Python tests passed**, including causal features, holdout isolation, upload rejection, report contents, map coordinates, station-event validation, model/horizon reuse, station-card selection and tab navigation.
- All five supported station/gas datasets trained successfully. Every model and 7-/14-/30-day view produced the expected number of predictions and ordered uncertainty bands.
- Browser: clicking the South Pole marker changed the sidebar, selected marker details, latest observation, forecast and model to that station.
- Browser: zoom in/out, site focus, world reset and a pointer drag changed the map view as expected.
- Browser: “View selected forecast” selected the Forecast tab and displayed that station's outlook.
- Browser: Model lab and Data studio rendered their metrics, charts and controls.
- Browser: a real daily CSV uploaded, trained and appeared as a selected local map station with its entered name and coordinates. Selecting a reference station returned to NOAA mode.
- Browser: the 30-day horizon updated forecast dates/metrics, then the 14-day view was restored.
- Bundled world geometry's SHA-256 checksum matches `assets/map_provenance.json`.

The cached NOAA snapshot still ends in December 2025. Forecasts retain their actual origin dates; repairs do not fabricate live measurements or spatial predictions between stations.
