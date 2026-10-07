"""Hard tests: boundaries, failure modes, scientific invariants and the shipped artefacts' consistency."""
import json
from io import BytesIO
from pathlib import Path
import numpy as np
import pytest
from affine import Affine
from PIL import Image
from rasterio.io import MemoryFile
from monitor import catalog, scenes
from monitor.analysis import forest_analysis, lake_analysis
from monitor.exports import bundle, geotiff_bytes, polygons, rgb
from monitor.indices import forest_screen, indices, ratio, water_screen
from monitor.learning import baseline_forest_prior, features, reference_labels, score, train
from monitor.scenes import Scene, assert_aligned, from_geotiff, utm_grid, validate_bbox
from monitor.views import scene_map, selection_map, swipe_html
from monitor.workspace import region_records, save_review, load_reviews, reviewed_geojson, analysis_key

ROOT = Path(__file__).resolve().parents[1]
T = Affine(30, 0, 500000, 0, -30, 2800000)


def scene(h=20, w=20, year=2020, ndvi_hi=True, crs="EPSG:32646"):
    d = np.zeros((8, h, w), np.float32)
    d[0], d[1], d[2] = .04, .06, .05                     # blue green red
    d[3] = .5 if ndvi_hi else .06                        # nir (NDVI .82 vs .09)
    d[4], d[5], d[6], d[7] = .2, .2, .08, 4
    return Scene(d, T, crs, {"id": f"S{year}", "datetime": f"{year}-02-01"})


# ------------------------------------------------------------------ grids and boxes
@pytest.mark.parametrize("bbox,epsg", [([-64.60, -9.70, -64.52, -9.62], 32720), ([93.77, 24.47, 93.83, 24.53], 32646),
                                       ([179.85, 10, 179.95, 10.1], 32660), ([-179.95, -10.1, -179.85, -10], 32701),
                                       ([5.0, -0.05, 5.1, 0.15], 32631), ([5.0, -0.15, 5.1, 0.05], 32731)])
def test_utm_zone_and_hemisphere(bbox, epsg):
    assert utm_grid(bbox)[0] == f"EPSG:{epsg}"


@pytest.mark.parametrize("bbox", [[0, 0, 0, 0.1], [1, 0, 0, 0.1], [0, 5, 0.1, 5], [0, 0, 0.1, float("nan")], [0, 0, float("inf"), 1],
                                  [-181, 0, -180.5, 0.1], [0, 81, 0.1, 81.1], [0, 0, 0.5, 0.1], [0, 0, 0.1, 0.31], [0, 0, 0.1], "bad"])
def test_invalid_boxes_are_refused(bbox):
    with pytest.raises(ValueError):
        validate_bbox(bbox)


def test_pixel_cap_and_pixel_area():
    with pytest.raises(ValueError, match="million"):
        utm_grid([0, 0, 0.3, 0.3], resolution=10)
    assert scene().pixel_area_m2 == 900 and np.isclose(scene().pixel_area_m2 * 400 / 1e4, 36)


# ------------------------------------------------------------------ scene validity and uploads
def test_validity_needs_good_class_and_finite_bands():
    s = scene()
    s.data[7, 0, :4] = [4, 5, 6, 7]; s.data[2, 1, 0] = np.nan; s.data[7, 2, :3] = [3, 8, 9]
    v = s.valid
    assert v[0].tolist()[:4] == [True, True, True, False] and not v[1, 0] and not v[2, :3].any() and v[5, 5]


def _tif(count=8, crs="EPSG:32646", w=20, h=20, dtype="float32", fill=.1, scl=4, nodata=None):
    arr = np.full((count, h, w), fill, dtype)
    if count == 8: arr[7] = scl
    with MemoryFile() as m:
        kw = dict(driver="GTiff", width=w, height=h, count=count, dtype=dtype, transform=T)
        if crs: kw["crs"] = crs
        if nodata is not None: kw["nodata"] = nodata
        with m.open(**kw) as d: d.write(arr)
        return m.read()


def test_geotiff_validation_matrix():
    assert from_geotiff(_tif(), 1.0, "2020-01-01", "ok").shape == (20, 20)
    for kwargs, msg in [(dict(count=7), "8-band"), (dict(crs=None), "projected"), (dict(w=1100, h=1000), "million"), (dict(fill=9000.0), "scaled")]:
        with pytest.raises(ValueError, match=msg): from_geotiff(_tif(**kwargs), 1.0, "2020-01-01")
    with pytest.raises(ValueError): from_geotiff(_tif(crs="EPSG:4326"), 1.0, "2020-01-01")                # degrees cannot measure hectares
    assert from_geotiff(_tif(dtype="uint16", fill=1000, scl=4), 1e-4, "2020-01-01").data[0].max() == pytest.approx(.1)   # DN x 10,000 encoding
    with pytest.raises(ValueError): from_geotiff(b"not a tiff", 1.0, "2020-01-01")


def test_nodata_pixels_are_excluded_not_treated_as_zero_reflectance():
    arr = np.full((8, 10, 10), .1, np.float32); arr[7] = 4; arr[:7, 0, 0] = -9999
    with MemoryFile() as m:
        with m.open(driver="GTiff", width=10, height=10, count=8, dtype="float32", crs="EPSG:32646", transform=T, nodata=-9999) as d: d.write(arr)
        s = from_geotiff(m.read(), 1.0, "2020-01-01")
    assert not s.valid[0, 0] and s.valid[1, 1]


def test_alignment_and_date_order():
    a, b = scene(year=2020), scene(year=2024)
    assert_aligned(a, b)
    same_day = scene(year=2020)
    with pytest.raises(ValueError, match="later"): assert_aligned(a, same_day)
    bad = scene(year=2024); bad.transform = Affine(30, 0, 500030, 0, -30, 2800000)
    with pytest.raises(ValueError): assert_aligned(a, bad)
    with pytest.raises(ValueError): assert_aligned(a, scene(h=21, year=2024))
    with pytest.raises(ValueError): assert_aligned(a, scene(year=2024, crs="EPSG:32647"))


# ------------------------------------------------------------------ catalogue logic without the network
def item(**props):
    return {"properties": props}


@pytest.mark.parametrize("props,asset,expect", [
    ({"s2:processing_baseline": "05.00"}, {"raster:bands": [{"scale": .0001, "offset": -.1}]}, (.0001, -.1)),
    ({"s2:processing_baseline": "03.00"}, {"raster:bands": [{"scale": .0001, "offset": -.1}]}, (.0001, 0.0)),
    ({"s2:processing_baseline": "05.00", "earthsearch:boa_offset_applied": True}, {"raster:bands": [{"offset": -.1}]}, (.0001, 0.0)),
    ({}, {}, (.0001, 0.0)), ({"s2:processing_baseline": "04.00"}, {"raster:bands": [{"scale": 2e-4, "offset": -.2}]}, (2e-4, -.2))])
def test_reflectance_scale_and_offset_rules(props, asset, expect):
    assert catalog.reflectance_parameters(item(**props), asset) == pytest.approx(expect)


def test_search_requires_full_coverage_and_sorts_by_cloud(monkeypatch):
    feats = [{"id": "partial", "bbox": [0.0, 0.0, 0.05, 0.1], "properties": {"eo:cloud_cover": 1}},
             {"id": "b", "bbox": [-1, -1, 1, 1], "properties": {"eo:cloud_cover": 9}},
             {"id": "a", "bbox": [-1, -1, 1, 1], "properties": {"eo:cloud_cover": 2}}]
    class R:
        def raise_for_status(self): pass
        def json(self): return {"features": feats}
    sent = {}
    monkeypatch.setattr(catalog.requests, "post", lambda url, json, timeout: (sent.update(json), R())[1])
    got = catalog.search([0.0, 0.0, 0.1, 0.1], "2020-01-01", "2020-03-01")
    assert [f["id"] for f in got] == ["a", "b"] and sent["query"]["eo:cloud_cover"]["lt"] == 15 and sent["collections"] == ["sentinel-2-c1-l2a"]
    with pytest.raises(ValueError, match="before"): catalog.search([0.0, 0.0, 0.1, 0.1], "2020-03-01", "2020-01-01")
    feats.clear()
    with pytest.raises(ValueError, match="No covering"): catalog.search([0.0, 0.0, 0.1, 0.1], "2020-01-01", "2020-03-01")


def test_fetch_pair_rejects_overlap_and_unusable_scenes(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="overlap"): catalog.fetch_pair([0, 0, .1, .1], ["2020-01-01", "2020-06-01"], ["2020-05-01", "2020-09-01"], tmp_path)
    monkeypatch.setattr(catalog, "search", lambda *a, **k: [{"id": "x"}] * 3)
    cloudy = scene(); cloudy.data[7] = 9
    monkeypatch.setattr(catalog, "fetch_scene", lambda item, grid, log=None: cloudy)
    with pytest.raises(ValueError, match="insufficient clear"): catalog.fetch_pair([0, 0, .1, .1], ["2020-01-01", "2020-02-01"], ["2024-01-01", "2024-02-01"], tmp_path)


def test_hansen_tile_names_across_hemispheres():
    import inspect, re
    names = {}
    for bbox, want in [([-64.60, -9.70, -64.52, -9.62], "00N_070W"), ([93.77, 24.47, 93.83, 24.53], "30N_090E"), ([20.1, -3.5, 20.2, -3.4], "00N_020E"), ([-72.3, 14.2, -72.2, 14.3], "20N_080W")]:
        grid = utm_grid(bbox)
        urls = []
        monkey = catalog.read_remote_grid
        catalog.read_remote_grid = lambda url, g, **k: (urls.append(url), np.zeros((grid[3], grid[2])))[1]
        try: catalog.hansen_reference(bbox, grid, "/tmp/polaris-hansen-test")
        finally: catalog.read_remote_grid = monkey
        names[want] = re.search(r"_(\d\d[NS]_\d{3}[EW])\.tif", urls[0]).group(1)
        assert names[want] == want, (bbox, names[want])
    with pytest.raises(ValueError, match="one Hansen tile"): catalog.hansen_reference([9.95, 0.1, 10.05, 0.2], utm_grid([9.95, 0.1, 10.05, 0.2]), "/tmp/polaris-hansen-test")


# ------------------------------------------------------------------ indices and the screens
def test_ratio_handles_zero_nan_and_tiny_denominators():
    out = ratio(np.array([1., 0., np.nan, 1.]), np.array([0., 0., 1., 1e-9]))
    assert np.isnan(out).all()
    assert ratio(np.array([1.]), np.array([2.]))[0] == .5


def test_forest_loss_exact_pixels_and_connectivity():
    b, a = scene(), scene(year=2024)
    a.data[3, 2:7, 2:7] = .06                                                  # a 5x5 clear-cut
    a.data[3, 12, 12] = .06; a.data[3, 13, 13] = .06                           # two diagonal pixels: not 4-connected
    r = forest_analysis(b, a, min_pixels=4)
    assert r["loss"].sum() == 25 and r["summary"]["candidate_loss_area_ha"] == pytest.approx(25 * .09) and r["summary"]["alert_regions"] == 1
    assert forest_analysis(b, a, min_pixels=1)["summary"]["alert_regions"] == 3
    assert forest_analysis(b, a, min_pixels=26)["loss"].sum() == 0


def test_thresholds_are_monotone():
    b, a = scene(), scene(year=2024)
    rng = np.random.default_rng(0); a.data[3] = rng.uniform(.06, .5, a.shape)
    areas = [forest_analysis(b, a, drop=d, min_pixels=1)["loss"].sum() for d in (.05, .1, .2, .4, .6)]
    assert areas == sorted(areas, reverse=True)
    veg = [forest_analysis(b, a, vegetation=v, min_pixels=1)["loss"].sum() for v in (.3, .5, .7, .85)]
    assert veg == sorted(veg, reverse=True)
    patch = [forest_analysis(b, a, min_pixels=m)["loss"].sum() for m in (1, 2, 4, 8, 30)]
    assert patch == sorted(patch, reverse=True)


def test_no_loss_scene_and_all_invalid_scene_do_not_crash_or_invent_loss():
    b, a = scene(), scene(year=2024)
    r = forest_analysis(b, a); assert r["loss"].sum() == 0 and r["alerts"].empty and r["summary"]["alert_regions"] == 0
    a.data[7] = 9
    r = forest_analysis(b, a); assert r["summary"]["observed_pair_pct"] == 0 and r["loss"].sum() == 0 and r["summary"]["mean_ndvi_change"] is None
    json.dumps(r["summary"], allow_nan=False)


def test_forest_prior_shape_is_enforced():
    with pytest.raises(ValueError, match="share the observation grid"):
        forest_analysis(scene(), scene(year=2024), forest_prior=np.ones((3, 3), bool))


def lake_scene(year, bump=0.0):
    s = scene(year=year)
    s.data[3] = .01; s.data[4] = .005; s.data[5] = .003; s.data[7] = 6          # open water everywhere
    s.data[6] = .04 + bump                                                      # red edge drives NDCI
    return s


def test_lake_indicators_and_alert_area():
    b, a = lake_scene(2020), lake_scene(2024, bump=0.0)
    a.data[6, :10] += .08                                                        # NDCI rises on the upper half only
    r = lake_analysis(b, a, algae_change=.1)
    assert r["summary"]["common_water_ha"] == pytest.approx(20 * 20 * .09, abs=1e-6)     # the scene edge is not a shoreline, so edge water is kept
    assert 0 < r["summary"]["algae_proxy_increase_ha"] <= r["summary"]["common_water_ha"]
    assert (r["alerts"] & ~r["common"]).sum() == 0
    hi = lake_analysis(b, a, algae_change=.35)["summary"]["algae_proxy_increase_ha"]
    assert hi <= r["summary"]["algae_proxy_increase_ha"]
    assert all(row["change"] is not None for row in r["summary"]["indicators"]) and r["table"].shape[0] == 3


def test_lake_needs_enough_common_water_and_uses_supplied_masks():
    with pytest.raises(ValueError, match="Too few"):
        lake_analysis(scene(), scene(year=2024))                                 # vegetation, no water
    b, a = lake_scene(2020), lake_scene(2024)
    left = np.zeros(b.shape, bool); left[:, :8] = True
    r = lake_analysis(b, a, water_masks=(left, left))
    assert "U-Net" in r["summary"]["method"] and r["common"].sum() < left.sum()  # eroded by one pixel


# ------------------------------------------------------------------ learning
def test_reference_labels_year_rules():
    h = w = 6
    ref = {"lossyear": np.array([[0, 19, 20, 21, 23, 24], [25, 0, 0, 0, 0, 0]] + [[0] * 6] * 4, np.uint8), "treecover2000": np.full((h, w), 80, np.uint8), "datamask": np.ones((h, w), np.uint8)}
    b, a = scene(year=2019), scene(year=2024)
    y, usable = reference_labels(b, a, ref)
    assert y[0].tolist() == [0, 0, 1, 1, 1, 0]                                   # loss strictly between the two years
    assert usable[0].tolist() == [True, False, True, True, True, False]          # baseline-year and comparison-year losses are ambiguous
    assert usable[1, 0]                                                           # loss after the comparison image counts as "no loss yet"
    with pytest.raises(ValueError): reference_labels(scene(year=2024), scene(year=2019), ref)
    assert not baseline_forest_prior(b, ref)[0, 1] and baseline_forest_prior(b, ref)[0, 2]
    ref["treecover2000"][:] = 10
    assert not reference_labels(b, a, ref)[1].any()


def test_score_matches_hand_computation():
    y = np.array([1, 1, 1, 0, 0, 0, 0, 0]); p = np.array([.9, .8, .2, .7, .1, .1, .1, .1])
    s = score(y, p)
    assert s["confusion_matrix"] == {"tn": 4, "fp": 1, "fn": 1, "tp": 2}
    assert s["precision"] == pytest.approx(2 / 3) and s["recall"] == pytest.approx(2 / 3) and s["f1"] == pytest.approx(2 / 3) and s["iou"] == pytest.approx(.5)


def test_shipped_training_artefacts_are_consistent_and_leak_free():
    m = json.loads((ROOT / "models/metrics.json").read_text())
    for k in ("rf", "ndvi_baseline"):
        c = m[k]["confusion_matrix"]
        assert sum(c.values()) == m["holdout_samples"] and c["tp"] + c["fn"] == m["holdout_positive_samples"]
        assert m[k]["precision"] == pytest.approx(c["tp"] / (c["tp"] + c["fp"])) and m[k]["recall"] == pytest.approx(c["tp"] / (c["tp"] + c["fn"]))
        f1 = 2 * m[k]["precision"] * m[k]["recall"] / (m[k]["precision"] + m[k]["recall"]); assert m[k]["f1"] == pytest.approx(f1)
        assert m[k]["iou"] == pytest.approx(c["tp"] / (c["tp"] + c["fp"] + c["fn"]))
    assert len(m["features"]) == 16 and abs(sum(m["feature_importance"].values()) - 1) < 1e-6
    with np.load(ROOT / "models/sample_inference.npz") as z:
        tr, te = z["training"], z["holdout"]
        assert not (tr & te).any() and te.sum() == m["holdout_samples"] and z["reference"][te].sum() == m["holdout_positive_samples"]
        ct, ce = np.where(tr)[1], np.where(te)[1]
        assert ce.min() - ct.max() >= 6                                           # the six-column gap really exists
        assert np.isfinite(z["score"][te]).all()


def test_training_is_deterministic_and_split_is_geographic(tmp_path):
    b, a = scene(40, 60, 2019), scene(40, 60, 2024)
    rng = np.random.default_rng(1); a.data[3] = np.where(rng.random(a.shape) < .4, .06, .5)
    lossyear = np.where(rng.random(b.shape) < .4, 21, 0).astype(np.uint8)
    # make the label learnable: loss where the comparison nir fell
    lossyear = np.where(a.data[3] < .1, 21, 0).astype(np.uint8)
    ref = {"lossyear": lossyear, "treecover2000": np.full(b.shape, 90, np.uint8), "datamask": np.ones(b.shape, np.uint8)}
    _, m1 = train(b, a, ref, tmp_path / "a"); _, m2 = train(b, a, ref, tmp_path / "b")
    assert m1["rf"] == m2["rf"] and m1["rf"]["f1"] > .95
    with np.load(tmp_path / "a/sample_inference.npz") as z:
        assert (np.where(z["holdout"])[1].min() - np.where(z["training"])[1].max()) >= 6
    ref["lossyear"][:] = 0
    with pytest.raises(ValueError, match="Insufficient"): train(b, a, ref, tmp_path / "c")


# ------------------------------------------------------------------ exports, regions, reviews, views
def test_exports_are_georeferenced_and_json_is_strict(tmp_path):
    import rasterio, zipfile
    b, a = scene(), scene(year=2024); a.data[3, 2:7, 2:7] = .06
    r = forest_analysis(b, a, min_pixels=4)
    with MemoryFile(geotiff_bytes(r["delta"], a)) as m, m.open() as d:
        assert d.crs.to_string() == "EPSG:32646" and tuple(d.transform)[:6] == tuple(a.transform)[:6] and d.shape == a.shape
    geo = polygons(r["loss"], a); assert len(geo["features"]) == 1
    xs = [c[0] for c in geo["features"][0]["geometry"]["coordinates"][0]]; assert all(93 < x < 95 for x in xs)
    z = zipfile.ZipFile(BytesIO(bundle(r["summary"], b, a, {"ndvi_change": r["delta"]}, r["loss"], None, "a,b\n1,2\n")))
    assert {"summary.json", "report.md", "metadata.json", "review_regions.geojson", "ndvi_change.tif", "indicators.csv"} <= set(z.namelist())
    json.loads(z.read("summary.json"))


def test_regions_reviews_and_keys(tmp_path):
    b, a = scene(), scene(year=2024); a.data[3, 2:7, 2:7] = .06; a.data[3, 14:17, 14:17] = .06
    r = forest_analysis(b, a, min_pixels=4)
    rows, groups = region_records(r["loss"], a, r["delta"])
    assert rows.area_ha.tolist() == [2.25, .81] and rows.latitude.between(24, 26).all() and rows.longitude.between(93, 95).all()
    path = tmp_path / "r.json"; assert load_reviews(path) == {}
    rv = save_review(path, {}, 1, "Likely change", "n"); assert load_reviews(path)["1"]["status"] == "Likely change" and rv["1"]["note"] == "n"
    for bad in (("Nonsense", "x"), ("Unclear", "x" * 2001)):
        with pytest.raises(ValueError): save_review(path, rv, 1, *bad)
    assert load_reviews(path)["1"]["status"] == "Likely change"                 # a rejected save leaves the file untouched
    k1 = analysis_key(b, a, r["loss"]); assert k1 == analysis_key(b, a, r["loss"])
    other = r["loss"].copy(); other[0, 0] = True; assert analysis_key(b, a, other) != k1
    geo = reviewed_geojson(groups, a, rows, rv); assert {f["properties"]["status"] for f in geo["features"]} == {"Likely change", "Needs review"}


def test_views_escape_labels_and_maps_build():
    html_out = swipe_html(rgb(scene()), rgb(scene()), "<script>alert(1)</script>", 'x"onload="y')
    assert "<script>alert(1)</script>" not in html_out and "&lt;script&gt;" in html_out and 'x"onload' not in html_out
    s = scene(); r = forest_analysis(scene(), scene(year=2024))
    assert "leaflet" in scene_map(s, rgb(s))._repr_html_().lower() and "leaflet" in selection_map([93.77, 24.47, 93.83, 24.53])._repr_html_().lower()


def test_rgb_inputs_limits(tmp_path):
    from monitor.image_inputs import compare_rgb, read_rgb
    big = BytesIO(); Image.new("1", (3000, 3000)).save(big, format="PNG")
    with pytest.raises(ValueError, match="four million"): read_rgb(big.getvalue())
    with pytest.raises(Exception): read_rgb(b"nope")
    img = np.full((20, 20, 3), 120, np.uint8)
    with pytest.raises(ValueError): compare_rgb(img, img[:10], np.ones((20, 20), bool))
    with pytest.raises(ValueError): compare_rgb(img, img, np.zeros((20, 20), bool))
    after = img.copy(); after[:5, :5] = [250, 20, 20]
    res = compare_rgb(img, after, np.ones((20, 20), bool), .12, 4); assert res["mask"].sum() == 25
    assert compare_rgb(img, img, np.ones((20, 20), bool))["mask"].sum() == 0
    t = Image.new("RGBA", (10, 10), (0, 0, 0, 0)); o = BytesIO(); t.save(o, format="PNG")
    assert not read_rgb(o.getvalue())[1].any()                                   # transparent pixels are not comparable


def test_unet_handles_tiny_and_invalid_scenes():
    from monitor import water_model
    if not water_model.available(): pytest.skip("U-Net weights not installed")
    s = lake_scene(2020); s.data = s.data[:, :9, :11].copy(); s.data[:6] += np.random.default_rng(0).random(s.data[:6].shape).astype(np.float32) * .02
    m = water_model.segment(s); assert m.shape == (9, 11) and m.dtype == bool and not (m & ~s.valid).any()
    s.data[7] = 9
    with pytest.raises(ValueError): water_model.segment(s)
