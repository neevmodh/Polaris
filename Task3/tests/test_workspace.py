from io import BytesIO
import zipfile
import json
import numpy as np
import pytest
from affine import Affine
from PIL import Image
from monitor.scenes import Scene
from monitor.workspace import (drawn_bbox, timeline_frame, region_records, save_review,
                               load_reviews, analysis_key, reviewed_geojson)
from monitor.image_inputs import compare_rgb, read_rgb, rgb_package
from monitor.exports import bundle


def scene(day, nir=.7):
    a = np.full((8, 10, 10), .1, dtype=np.float32)
    a[3] = nir
    a[7] = 4
    return Scene(a, Affine(30, 0, 500000, 0, -30, 2700000), "EPSG:32646", {"id": day, "datetime": day})


def test_drawn_rectangle_bounds_and_size_limits():
    feature = {"geometry": {"type": "Polygon", "coordinates": [[[93.8, 24.5], [93.85, 24.5], [93.85, 24.55], [93.8, 24.55], [93.8, 24.5]]]}}
    assert drawn_bbox(feature) == [93.8, 24.5, 93.85, 24.55]
    feature["geometry"]["coordinates"][0][1][0] = 94.2
    with pytest.raises(ValueError, match="0.3"):
        drawn_bbox(feature)


def test_timeline_uses_same_clear_support_and_real_dates():
    a, b, c = scene("2020-01-01"), scene("2022-01-01", .5), scene("2024-01-01", .3)
    b.data[7, :2] = 9
    c.data[7, -2:] = 9
    # Both invalid strips must be excluded at every date, not just their own date.
    table, keys = timeline_frame([c, a, b], "forest")
    assert table.date.tolist() == ["2020-01-01", "2022-01-01", "2024-01-01"]
    assert table.matched_support_ha.tolist() == [5.4] * 3
    assert table.NDVI.is_monotonic_decreasing
    assert keys[0] == "NDVI"
    with pytest.raises(ValueError):
        timeline_frame([a, a], "forest")


def test_review_ids_persist_and_export_with_matching_geometries(tmp_path):
    a, b = scene("2020-01-01"), scene("2024-01-01")
    mask = np.zeros(a.shape, bool)
    mask[1:3, 1:3] = True
    mask[6:9, 6:9] = True
    rows, groups = region_records(mask, b, np.full(a.shape, -.4))
    path = tmp_path / "review.json"
    assert load_reviews(path) == {}
    rid = int(rows.iloc[0].region)
    saved = save_review(path, {}, rid, "Unclear", "Possible seasonal change")
    assert load_reviews(path) == saved
    geo = reviewed_geojson(groups, b, rows, saved)
    annotated = next(f for f in geo["features"] if f["properties"]["region"] == rid)
    assert annotated["properties"]["status"] == "Unclear"
    assert annotated["properties"]["area_ha"] == .81
    assert 93 < annotated["geometry"]["coordinates"][0][0][0] < 94
    old_key = analysis_key(a, b, mask)
    b.data[0, 0, 0] += .01
    assert analysis_key(a, b, mask) != old_key
    with pytest.raises(ValueError):
        save_review(path, saved, rid, "Confirmed pollution", "")


def test_rgb_change_is_brightness_robust_and_has_no_fake_geospatial_metrics():
    a = np.full((20, 20, 3), [40, 120, 40], dtype=np.uint8)
    b = a // 2
    valid = np.ones((20, 20), bool)
    unchanged = compare_rgb(a, b, valid)
    assert unchanged["summary"]["changed_pixels"] == 0
    b[3:8, 3:8] = [120, 60, 30]
    r = compare_rgb(a, b, valid)
    assert r["summary"]["changed_pixels"] == 25
    assert r["summary"]["changed_pct"] == 6.25
    assert "area_ha" not in r["summary"]
    with zipfile.ZipFile(BytesIO(rgb_package(a, b, r))) as z:
        assert "change_mask.png" in z.namelist()
        assert json.loads(z.read("summary.json"))["changed_pixels"] == 25
    with pytest.raises(ValueError, match="identical dimensions"):
        compare_rgb(a, b[:-1], valid)


def test_transparent_upload_pixels_are_excluded():
    a = np.zeros((10, 10, 4), dtype=np.uint8)
    a[..., :3] = [50, 100, 50]
    a[..., 3] = 255
    a[0, :, 3] = 0
    out = BytesIO()
    Image.fromarray(a).save(out, format="PNG")
    rgb, valid = read_rgb(out.getvalue())
    assert valid.sum() == 90
    assert rgb.shape == (10, 10, 3)


def test_satellite_zip_includes_timeline_and_human_reviews():
    a, b = scene("2020-01-01"), scene("2024-01-01")
    summary = {"analysis": "Test", "interpretation": "Screening only"}
    archive = bundle(summary, a, b, {}, np.zeros(a.shape, bool),
                     extras={"observation_timeline.csv": "date,NDVI\n2020-01-01,0.7",
                             "reviewed_regions.geojson": '{"type":"FeatureCollection","features":[]}'})
    with zipfile.ZipFile(BytesIO(archive)) as z:
        assert "observation_timeline.csv" in z.namelist()
        assert json.loads(z.read("reviewed_regions.geojson"))["features"] == []


def test_review_map_has_explicit_view_when_tab_is_initially_hidden():
    from monitor.views import scene_map
    from monitor.exports import rgb
    a = scene("2024-01-01")
    mask = np.zeros(a.shape, bool)
    mask[2:5, 2:5] = True
    rows, groups = region_records(mask, a, np.full(a.shape, -.3))
    geo = reviewed_geojson(groups, a, rows, {})
    m = scene_map(a, rgb(a), geo, int(rows.iloc[0].region))
    assert m.options["zoom"] >= 12
    assert abs(m.location[1] - rows.iloc[0].longitude) < .005
    assert not any(type(child).__name__ == "FitBounds" for child in m._children.values())
