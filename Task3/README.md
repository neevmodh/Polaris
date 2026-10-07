# Polaris · Satellite Monitor

A local Greenovators Track 3 prototype for **forest-loss screening** and **lake
water-quality indicators**, built from real Sentinel-2 satellite observations.

The application includes a trained random-forest forest-loss classifier, an NDVI
baseline, an optional upstream pretrained U-Net for water segmentation, side-by-side
maps, quality masking, geospatial exports, provenance and honest model evaluation.

## Five expanded workspace features

1. **Map input and geographic context.** Choose `Fetch a custom region`, draw a
   rectangle, click `Use this map selection`, then fetch the two date windows.
   The observation viewer also places real imagery on an OpenStreetMap basemap.
2. **Image input studio.** Upload PNG/JPEG before/after pairs for visible-color
   screening or eight-band GeoTIFFs for multispectral analysis. Preview actual
   inputs and inspect individual reflectance bands and SCL quality classes.
3. **Swipe comparison.** Move an interactive divider between aligned observations,
   with optional candidate-change overlays, for both satellite and RGB inputs.
4. **Timeline and trends.** Both prepared studies contain three real acquisitions.
   Add more dates using an aligned GeoTIFF or a public satellite date-window fetch.
   Trends use the same clear support across every included date; export their CSV.
5. **Persistent review queue.** Inspect ranked candidate patches on a map and in
   image crops, save a decision and notes, filter by review status, and export
   annotated GeoJSON/CSV. Reviews are tied to the actual images and candidate mask,
   so changed inputs or masks do not inherit unrelated decisions.

## Run

```bash
cd /Users/neev/Downloads/POLARIS/Task3
bash run.sh
```

Open **http://localhost:8503**. Prepared real case studies and model artifacts are
stored locally so the core dashboard works without satellite APIs during the demo.
Fonts may fall back to system fonts when offline. Map basemap tiles require
internet access; cached image comparisons, timelines and review calculations work
locally. Uploaded images stay on the local server.

To install from scratch (Python 3.12 recommended):

`requirements.lock.txt` records the exact versions installed and tested in this
workspace; use it instead of `requirements-water.txt` for the same environment.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-water.txt
.venv/bin/python scripts/bootstrap_data.py --preset all
.venv/bin/python scripts/train_forest.py
.venv/bin/python scripts/setup_water_model.py
.venv/bin/python scripts/bootstrap_timeline.py
.venv/bin/python scripts/build_reports.py
bash run.sh
```

If the `references/` directories are omitted when packaging, clone the four exact
repos documented in THIRD_PARTY_NOTICES.md first. Skip Git LFS smudging when cloning
the lake repo (`git -c filter.lfs.process= -c filter.lfs.smudge= -c filter.lfs.required=false clone ...`)
and let `setup_water_model.py` download the exact verified U-Net weights.

## Prepared case studies

- **Rondônia forest frontier, Brazilian Amazon:** a compact region observed in the
  same season in 2019 and 2024, with Hansen annual tree-cover loss as an external
  map reference. Exact selected acquisitions live in `data/forest/*` metadata.
- **Loktak Lake, Manipur, India:** clear observations from early 2020 and early 2024.
  Open-water masks and spectral algae/turbidity proxies are compared on the same
  observed water pixels. No field-calibrated pollutant concentration is claimed.

## What the AI does

### Forest loss

The new random forest learns 16 paired-image features (NDVI, NBR, NDMI, MNDWI and
reflectance changes). Labels come from Hansen GFC 2024 v1.12, restricted to
baseline canopy ≥30% and pixels not already lost before the baseline year.
Acquisition endpoint years are excluded from evaluation because annual loss labels
cannot resolve whether loss occurred before or after a satellite acquisition.

The fixed spatial split uses the western 70% for training and the eastern 30% for
testing, with a six-column exclusion gap. Metrics include precision, recall, F1,
IoU, average precision and confusion counts, alongside an NDVI baseline.
`models/metrics.json` contains actual measurements, not advertised accuracy.

Evaluation is **agreement with a reference map in one region**, not independent
field validation or generalization across countries. Model scores are uncalibrated.
The map masks previously low-NDVI pixels and removes small candidate patches.
The cached forest study also restricts alerts to historical canopy with no Hansen
loss through the baseline year, preventing previously cleared, vegetated fields
from being counted as new forest loss. Regrowth is conservatively excluded.
Custom/uploaded scenes have no independent forest-support map and explicitly use
high baseline NDVI as a vegetation screening proxy.
Reference-test metrics are computed before these user-adjustable map filters and
on a different restricted population; map hectares must not be inferred from F1.

### Lake analysis

The upstream Apache-2.0 U-Net is a **water segmentation** model, not a pollution
classifier. Its six-band inputs and normalization follow the original repository,
with overlap-tiled inference and cloud masking added. The transparent spectral
mask is available as an alternative and is the default for lake screening.

NDCI `(B05-B04)/(B05+B04)`, NDTI `(B04-B03)/(B04+B03)`, and the visible ratio
`(B04+B03)/B02` are unitless proxies. The red-edge and visible ratio forms adapt
the referenced `waterquality` algorithms to nearby Sentinel-2 wavelengths.
They do not establish NTU, chlorophyll concentration, sewage, bacteria, heavy
metals or safe drinking water. Local samples and calibration are needed for that.
Clouds, shadows, snow, uncertain SCL pixels and a one-pixel shoreline margin are
excluded. Floating mats and shallow bottoms remain material confounders.

## Custom observations

Use **Fetch a custom region** to enter west/south/east/north, two non-overlapping
date windows and a region name. The app requests a clear scene covering the ROI,
checks local clear-pixel coverage, reads only cropped COG windows, applies STAC
scale/offset values, and reprojects to a shared 30 m UTM grid.

The public HTTPS data path needs network access but no Earth Engine account or API
key. Choose a compact ROI (sides ≤0.3°, at most one million pixels); consider
seasonally matched dates. One acquisition per window is used, not a temporal
median composite. Atmospheric differences and missed changes may affect outputs.

**Upload aligned GeoTIFFs** supports eight bands in this fixed order:
`B02, B03, B04, B08, B11, B12, B05, SCL`. Use a projected CRS in metres, identical
grid/extent, and either already-scaled surface reflectance or harmonized DN ×10,000.
Raw ESA DN with a BOA offset must be converted first. Upload-ready files are
included in `outputs/forest/` and `outputs/lake/` for the prepared acquisitions.

**Upload PNG / JPEG images** accepts two pre-aligned images with the same pixel
dimensions, up to four million pixels. You must confirm alignment. The comparison
uses changes in RGB chromatic proportions, which reduces overall brightness
differences, plus a minimum patch filter. It reports changed-pixel percentages,
never hectares, NDVI, trained forest predictions or pollutant concentrations.
Clouds, viewpoint, exposure and season can still create color changes. Transparent
pixels are excluded; other cloud masking is unavailable without SCL.

Timeline GeoTIFFs must share the current pair's grid and have acquisition dates
strictly between the two endpoints. Timeline lake support always uses the
spectral mask, including when the two-date viewer selects the U-Net. Removing a
date from the timeline selection leaves its cached observation available later.

Local review records are saved under `data/reviews/`; additional observations
are stored under `data/timeline/`. Back up these folders with the project when
packaging a demo. Human review statuses do not establish independently verified
deforestation or water quality.

## Exports and reproducibility

Each analysis ZIP contains JSON summaries, a Markdown report, before/after images,
GeoTIFF layers, review polygons in WGS84 GeoJSON, CSV indicators and provenance.
Static prepared outputs are in `outputs/forest/` and `outputs/lake/`.
`outputs/forest/sample_inference.csv` contains reproducible held-out predictions.

```bash
.venv/bin/python scripts/train_forest.py
.venv/bin/python scripts/build_reports.py
.venv/bin/python -m pytest -q
```

Tests check clear-pixel area accounting, alignment, scaling, missing observations,
water support, annual-label ambiguity, exports and both dashboard modes. Synthetic
arrays exist only as unit-test fixtures; the app has no synthetic fallback.
See [VALIDATION.md](VALIDATION.md) for the completed checks and measured results.

## Jury demo / 3 minutes

1. Open the forest case study. Show dates, actual scenes, coverage and candidate
   loss regions. Switch between true color, NDVI changes and ML scores.
2. Switch the detector to the NDVI baseline and explain the different findings.
   Open **Model & evidence** to show the spatial holdout and actual metrics.
3. Switch to Loktak Lake. Show same-pixel water indicators and compare the spectral
   mask with the pretrained U-Net. Explain what the proxies can establish.
4. Download an analysis package. Show source IDs, GeoJSON regions and GeoTIFFs.

## Repositories and attribution

Original repository sources are preserved in `references/`. TerraVision supplies
the baseline workflow, waterquality supplies spectral algorithm references, and
the lake repository supplies the actual U-Net architecture/weights. Forest-CD is
a research reference; its VHR network is not this app's forest model.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for revisions, licenses and changes.

No named-site deployment, verified deforestation, measured carbon savings or
field-validated pollution detection is claimed by this prototype.
