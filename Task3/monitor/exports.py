"""Reports, georeferenced rasters and vector alerts built from actual analysis."""
from io import BytesIO
import json
import zipfile
import numpy as np
from PIL import Image
from rasterio.features import shapes
from rasterio.io import MemoryFile
from rasterio.warp import transform_geom


def json_text(obj):
    return json.dumps(obj, indent=2, allow_nan=False)


def rgb(scene):
    a = np.moveaxis(scene.data[[2, 1, 0]], 0, -1)
    # Shared, fixed reflectance stretch across dates; not misleading per-image normalization.
    a = np.nan_to_num(np.clip(a / 0.3, 0, 1)) ** (1 / 1.5)
    a[~scene.valid] = [0.09, 0.13, 0.12]
    return (a * 255).astype(np.uint8)


def overlay(scene, mask, color=(255, 96, 77)):
    a = rgb(scene).astype(float)
    a[mask] = a[mask] * 0.35 + np.array(color) * 0.65
    return a.astype(np.uint8)


def png_bytes(image):
    out = BytesIO()
    Image.fromarray(image).save(out, format="PNG")
    return out.getvalue()


def geotiff_bytes(array, scene, nodata=np.nan):
    array = np.asarray(array)
    if array.ndim == 2:
        array = array[None]
    with MemoryFile() as mem:
        with mem.open(driver="GTiff", width=scene.shape[1], height=scene.shape[0],
                      count=len(array), dtype=array.dtype, crs=scene.crs, transform=scene.transform,
                      nodata=nodata, compress="deflate") as dst:
            dst.write(array)
        return mem.read()


def polygons(mask, scene):
    features = []
    for geom, value in shapes(mask.astype(np.uint8), mask=mask, transform=scene.transform):
        if value != 1:
            continue
        features.append({"type": "Feature", "geometry": transform_geom(scene.crs, "EPSG:4326", geom),
                         "properties": {"status": "screening alert; requires review"}})
    return {"type": "FeatureCollection", "features": features}


def bundle(summary, before, after, arrays, mask, metrics=None, table_csv=None, extras=None):
    report = ["# Polaris / Satellite Monitor", "", f"Analysis: {summary['analysis']}",
              f"Region: {summary.get('region', 'Custom region')}",
              f"Baseline: {before.metadata.get('datetime', 'User supplied')}",
              f"Comparison: {after.metadata.get('datetime', 'User supplied')}", "",
              "## Results", "", "```json", json_text(summary), "```", "",
              "## Interpretation", "", summary["interpretation"], "",
              "## Provenance", "", f"Before: {before.metadata['id']}",
              f"After: {after.metadata['id']}", f"CRS: {before.crs}",
              f"Analysis pixel area: {before.pixel_area_m2} m²", "",
              "Refer to metadata.json for original image sources, scaling and processing details."]
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("summary.json", json_text(summary))
        z.writestr("report.md", "\n".join(report))
        z.writestr("metadata.json", json_text({"before": before.metadata, "after": after.metadata}))
        z.writestr("before_rgb.png", png_bytes(rgb(before)))
        z.writestr("after_rgb.png", png_bytes(rgb(after)))
        z.writestr("review_overlay.png", png_bytes(overlay(after, mask)))
        z.writestr("review_regions.geojson", json_text(polygons(mask, after)))
        for name, array in arrays.items():
            z.writestr(f"{name}.tif", geotiff_bytes(array.astype(np.float32), after))
        if metrics:
            z.writestr("model_metrics.json", json_text(metrics))
        if table_csv:
            z.writestr("indicators.csv", table_csv)
        for name, content in (extras or {}).items():
            z.writestr(name, content)
    return out.getvalue()
