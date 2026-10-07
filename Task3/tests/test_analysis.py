"""Physical/data-quality checks; synthetic arrays here are unit-test fixtures only."""
import json
from io import BytesIO
import zipfile
import numpy as np
import pytest
from affine import Affine
from rasterio.io import MemoryFile
from monitor.scenes import Scene, assert_aligned, utm_grid, from_geotiff
from monitor.catalog import reflectance_parameters
from monitor.indices import forest_screen, water_screen, ratio
from monitor.analysis import forest_analysis, lake_analysis
from monitor.exports import bundle
from monitor.learning import reference_labels


def scene(water=False, year=2020):
    data = np.zeros((8, 12, 12), dtype=np.float32)
    data[0], data[1], data[2] = .04, .06, .05
    data[3], data[4], data[5], data[6] = .5, .2, .2, .08
    data[7] = 4
    if water:
        data[3], data[4], data[5], data[7] = .01, .005, .003, 6
    return Scene(data, Affine(30, 0, 500000, 0, -30, 2800000), "EPSG:32646",
                 {"id": "TEST FIXTURE", "datetime": f"{year}-02-01", "source": "Unit-test fixture only"})


def test_clouds_and_unpaired_pixels_never_count_as_loss():
    b, a = scene(), scene(year=2024)
    a.data[3] = .04
    a.data[7, :, :4] = 9
    b.data[7, :, 4:8] = 3
    result = forest_analysis(b, a, min_pixels=1)
    assert result["loss"].sum() == 48
    assert result["summary"]["candidate_loss_area_ha"] == 4.32
    assert result["summary"]["observed_pair_pct"] == 33.33


def test_area_uses_projected_affine_determinant():
    b = scene()
    b.transform = Affine(30, 5, 500000, 4, -30, 2800000)
    assert b.pixel_area_m2 == 920
    with pytest.raises(ValueError, match="projected"):
        Scene(b.data, Affine(.001, 0, 93, 0, -.001, 24), "EPSG:4326", b.metadata)


def test_old_cleared_land_is_not_counted_as_new_forest_loss():
    b, a = scene(), scene(year=2024)
    a.data[3] = .04
    prior = np.zeros(b.shape, dtype=bool)
    prior[:, :6] = True
    r = forest_analysis(b, a, min_pixels=1, forest_prior=prior)
    assert r["loss"].sum() == 72
    assert r["summary"]["candidate_loss_area_ha"] == 6.48
    assert "Hansen" in r["summary"]["baseline_support"]


def test_misaligned_or_reversed_observations_are_rejected():
    b, a = scene(), scene(year=2024)
    a.transform = Affine(30, 0, 500001, 0, -30, 2800000)
    with pytest.raises(ValueError, match="share"):
        assert_aligned(b, a)
    with pytest.raises(ValueError, match="later"):
        assert_aligned(scene(year=2024), scene())


def test_cloud_class_and_nan_reflectance_are_excluded():
    b = scene()
    b.data[7, 0, :8] = [0, 1, 2, 3, 7, 8, 9, 10]
    b.data[7, 1, 0] = 11
    b.data[0, 1, 1] = np.nan
    assert b.valid.sum() == 134


def test_no_water_is_reported_as_missing_analysis_not_zero_pollution():
    with pytest.raises(ValueError, match="Too few"):
        lake_analysis(scene(), scene(year=2024))


def test_lake_comparison_uses_common_water_and_excludes_shore():
    b, a = scene(water=True), scene(water=True, year=2024)
    a.data[7, :, :3] = 9
    a.data[6] = .12
    r = lake_analysis(b, a)
    # The one-pixel shore margin applies next to cloud and land, not at the scene edge (8 columns x 12 rows).
    assert r["common"].sum() == 96
    assert r["summary"]["common_water_ha"] == 8.64
    assert r["table"]["change"].iloc[0] > 0
    assert all(r["table"]["units"] == "unitless spectral proxy")


def test_scaling_does_not_subtract_boa_offset_twice():
    asset = {"raster:bands": [{"scale": .0001, "offset": -.1}]}
    assert reflectance_parameters({"properties": {"earthsearch:boa_offset_applied": True}}, asset) == (.0001, 0)
    assert reflectance_parameters({"properties": {"s2:processing_baseline": "02.13"}}, asset) == (.0001, 0)
    assert reflectance_parameters({"properties": {"s2:processing_baseline": "05.00"}}, asset) == (.0001, -.1)


def test_reference_annual_endpoint_ambiguity_is_excluded():
    b, a = scene(year=2019), scene(year=2024)
    loss = np.zeros(b.shape)
    loss[0, :6] = [18, 19, 20, 23, 24, 0]
    ref = {"treecover2000": np.full(b.shape, 100), "datamask": np.ones(b.shape), "lossyear": loss}
    y, valid = reference_labels(b, a, ref)
    assert valid[0, :6].tolist() == [False, False, True, True, False, True]
    assert y[0, 2] == 1 and y[0, 3] == 1


def test_geospatial_export_reopens_and_preserves_area_and_mask():
    b, a = scene(), scene(year=2024)
    a.data[3] = .04
    r = forest_analysis(b, a, min_pixels=1)
    payload = bundle(r["summary"], b, a, {"loss": r["loss"].astype(float)}, r["loss"])
    with zipfile.ZipFile(BytesIO(payload)) as z:
        summary = json.loads(z.read("summary.json"))
        assert summary["candidate_loss_area_ha"] == 12.96
        vector = json.loads(z.read("review_regions.geojson"))
        assert len(vector["features"]) == 1
        assert -180 <= vector["features"][0]["geometry"]["coordinates"][0][0][0] <= 180
        with MemoryFile(z.read("loss.tif")) as mem, mem.open() as src:
            assert src.crs.to_epsg() == 32646
            assert src.transform == a.transform
            assert src.read(1).sum() == 144


def test_oversized_and_invalid_regions_are_rejected():
    with pytest.raises(ValueError):
        utm_grid([93.8, 24.5, 93.7, 24.6])
    with pytest.raises(ValueError):
        utm_grid([0, 0, 2, 2])


def test_upload_requires_real_georeferencing_band_order_and_scaling():
    b = scene()
    with MemoryFile() as mem:
        with mem.open(driver="GTiff", count=8, width=12, height=12, dtype="float32",
                      crs=b.crs, transform=b.transform) as dst:
            dst.write(b.data)
        assert from_geotiff(mem.read()).valid.all()
    with MemoryFile() as mem:
        with mem.open(driver="GTiff", count=8, width=12, height=12, dtype="float32",
                      crs=b.crs, transform=b.transform) as dst:
            data = b.data.copy()
            data[:7] *= 10000
            dst.write(data)
        content = mem.read()
        with pytest.raises(ValueError, match="scaled"):
            from_geotiff(content)
        assert from_geotiff(content, scale=.0001).valid.all()
