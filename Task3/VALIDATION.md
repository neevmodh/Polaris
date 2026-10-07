# Validation · 7 October 2026

The complete local environment uses Python 3.12.14. Installed package versions
are recorded in `requirements.lock.txt`.

## Completed checks

- `python -m pytest -q`: **68 passed** (22 original and 46 in `tests/test_hard.py`), including forest and lake dashboard
  controls, real cached artifacts, pretrained U-Net inference, spatial alignment,
  clear-pixel accounting, reflectance scaling, year-label exclusions and exports.
- `python -m pip check`: no broken dependencies.
- Hard-test round (`tests/test_hard.py`, plus live-browser and live-network runs): UTM zones and
  hemispheres, bounding-box refusals, GeoTIFF validation (band count, CRS, scaling, nodata,
  corrupt bytes), catalogue offset and coverage rules, forest and lake invariants (exact pixel
  counts, connectivity, monotone thresholds), label-year rules, a hand-checked score function,
  consistency of the shipped `metrics.json` with its own confusion counts, a verified six-column
  train and holdout gap, deterministic retraining, georeferenced exports, escaped viewer labels,
  RGB limits and the U-Net on tiny and fully-masked scenes. A real fetch of Lake Naivasha
  (Kenya) through the app succeeded in about 40 seconds. Two defects were found and fixed:
  a corrupt GeoTIFF leaked GDAL's internal path as the error message, and a corrupt PNG or JPEG
  crashed the image studio with a raw traceback. Non-numeric bounds now get a plain message.
- Fixed in the hard-test round: the one-pixel shoreline erosion used to trim water along the scene
  border, where there is no shoreline, which understated Loktak's water by about 2.2 to 2.4%. The
  scene edge is now kept (`border_value=1`); cloud and land edges are still eroded. The Loktak
  figures below, the prepared outputs and the tests were updated together.
- Browser review: both real case studies render their imagery, comparison layers,
  measured areas and spectral tables. Selecting the pretrained U-Net produces
  different water support and recalculates the lake indicators.
- Expanded workspace checks: rectangle drawing reaches the coordinate inputs;
  the swipe divider changes the visible split; actual PNG before/after files are
  accepted by the upload controls; RGB analysis, transparent-pixel exclusion,
  matched-support timelines, persistent review IDs, annotated GeoJSON and ZIP
  additions pass the tests. Map view has an explicit center/zoom, including when
  its Streamlit tab initially renders hidden.
- A review note was submitted through the browser and its stored JSON record was
  inspected. The verification note was then cleared; no test classification is
  left in the user's review queue.
- Prepared exports rebuilt from the cached observations and saved model artifacts.
  The downloaded U-Net weights match the SHA-256 recorded by the upstream LFS
  pointer. Upstream licenses and revisions are retained.

## Forest reference agreement

The fixed eastern holdout contains 3,199 eligible pixels, including 731 reference
loss pixels, separated from 9,449 training pixels by a six-column gap.

| Method | Precision | Recall | F1 | IoU |
|---|---:|---:|---:|---:|
| Random forest | 0.772 | 0.834 | 0.802 | 0.670 |
| NDVI baseline | 0.782 | 0.706 | 0.742 | 0.590 |

These are measurements against Hansen annual tree-cover-loss labels in one
Brazilian region, without field validation or evidence of geographic
generalization. See `models/metrics.json` for the complete evaluation.

The default forest screening map identifies **245.43 ha** of candidate loss on
**1,138.41 ha** of eligible baseline forest support, with **99.79%** clear paired
coverage. User thresholds and patch filters affect mapped areas. Holdout metrics
and these filtered map areas use different populations.

## Lake screening

Loktak Lake has **93.0%** clear paired coverage. The pretrained U-Net gives
**703.17 ha** of comparable open water and **319.41 ha** above the default NDCI
increase threshold. The default spectral mask gives different water support,
which is expected because the masks use different methods. Prepared lake reports
use the U-Net and record that choice explicitly.

Lake values are unitless optical proxies. They are not validated pollutant
concentrations or a water-safety assessment. Independent reference segmentation
and paired local water samples remain needed for those claims.

Live fetching was exercised while preparing both case studies. Arbitrary regions
and uploaded third-party imagery were not independently validated. The cached
demo does not require network access.

## Intermediate observations

Both prepared timelines include an additional real Sentinel-2 observation:

- Forest: `S2B_T20LLQ_20210702T143728_L2A`, acquired 2 July 2021. The three-date
  matched baseline forest support is **1,138.23 ha**.
- Lake: `S2B_T46REN_20220319T042930_L2A`, acquired 19 March 2022. The three-date
  matched spectral open-water support is **897.39 ha**.

The timeline CSV and reviewed-region GeoJSON are included in the rebuilt prepared
analysis packages. Basemap tiles need internet access. RGB-only inputs provide
visible-color screening; they are not passed into the multispectral models.
