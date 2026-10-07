"""Georeferenced, quality-masked Sentinel-2 scenes and local raster inputs."""
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
import rasterio
import rasterio.errors
from affine import Affine
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds

BANDS = ("blue", "green", "red", "nir", "swir16", "swir22", "rededge1", "scl")


@dataclass
class Scene:
    data: np.ndarray
    transform: Affine
    crs: str
    metadata: dict

    def __post_init__(self):
        if self.data.ndim != 3 or self.data.shape[0] != 8:
            raise ValueError("A scene must contain seven reflectance bands plus SCL.")
        if not rasterio.crs.CRS.from_user_input(self.crs).is_projected:
            raise ValueError("Use a projected raster in metres; geographic degrees cannot measure hectares.")
        if rasterio.crs.CRS.from_user_input(self.crs).linear_units != "metre":
            raise ValueError("The projected CRS must use metres.")

    @property
    def valid(self):
        # Adapted from TerraVision's SCL approach. Class 7 is excluded conservatively.
        return np.isin(self.data[7], [4, 5, 6]) & np.isfinite(self.data[:7]).all(axis=0)

    @property
    def shape(self):
        return self.data.shape[1:]

    @property
    def pixel_area_m2(self):
        return abs(self.transform.a * self.transform.e - self.transform.b * self.transform.d)

    @property
    def bounds(self):
        return rasterio.transform.array_bounds(*self.shape, self.transform)

    def band(self, name):
        return self.data[BANDS.index(name)]

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {**self.metadata, "crs": self.crs, "transform": list(self.transform)[:6], "bands": list(BANDS)}
        np.savez_compressed(path, data=self.data.astype(np.float32), metadata=json.dumps(meta))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(str(z["metadata"]))
            return cls(z["data"], Affine(*meta["transform"]), meta["crs"], meta)


def assert_aligned(before, after):
    if before.shape != after.shape or before.crs != after.crs or not before.transform.almost_equals(after.transform):
        raise ValueError("Before and after scenes must share a CRS, pixel grid, extent and resolution.")
    t1, t2 = before.metadata.get("datetime"), after.metadata.get("datetime")
    if t1 and t2 and t1 >= t2:
        raise ValueError("The comparison scene must be later than the baseline scene.")


def utm_grid(bbox, resolution=30):
    west, south, east, north = validate_bbox(bbox)
    lon, lat = (west + east) / 2, (south + north) / 2
    zone = min(60, int((lon + 180) // 6) + 1)
    crs = f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"
    left, bottom, right, top = transform_bounds("EPSG:4326", crs, *bbox)
    width, height = int(np.ceil((right - left) / resolution)), int(np.ceil((top - bottom) / resolution))
    if width * height > 1_000_000:
        raise ValueError("Select a smaller region (maximum one million analysis pixels).")
    return crs, Affine(resolution, 0, left, 0, -resolution, top), width, height


def validate_bbox(bbox):
    if len(bbox) != 4 or not np.isfinite(bbox).all():
        raise ValueError("Enter west, south, east, north as four finite coordinates.")
    w, s, e, n = map(float, bbox)
    if not (-180 <= w < e <= 180 and -80 <= s < n <= 80):
        raise ValueError("Invalid bounds. Use west < east and south < north, between 80°S and 80°N.")
    if e - w > 0.3 or n - s > 0.3:
        raise ValueError("Keep each side below 0.3 degrees for this prototype.")
    return w, s, e, n


def read_remote_grid(url, grid, categorical=False, nodata=0):
    crs, transform, width, height = grid
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT=45,
                      GDAL_HTTP_MAX_RETRY=2, GDAL_HTTP_RETRY_DELAY=1,
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", VSI_CACHE=True):
        with rasterio.open(url) as src:
            with WarpedVRT(src, crs=crs, transform=transform, width=width, height=height,
                           src_nodata=nodata, nodata=np.nan, dtype="float32",
                           resampling=Resampling.nearest if categorical else Resampling.bilinear) as vrt:
                return vrt.read(1)


def from_geotiff(content, scale=1.0, date=None, name="Uploaded image"):
    """Read an uploaded 8-band raster. Unreadable files raise a plain ValueError instead of leaking GDAL's internal path."""
    try:
        return _from_geotiff(content, scale, date, name)
    except rasterio.errors.RasterioIOError as exc:
        raise ValueError(f"{name} could not be read as a GeoTIFF. Upload an uncorrupted .tif exported with the band order B02, B03, B04, B08, B11, B12, B05, SCL.") from exc


def _from_geotiff(content, scale, date, name):
    from rasterio.io import MemoryFile
    with MemoryFile(content) as mem:
        with mem.open() as src:
            if src.count != 8:
                raise ValueError("Upload an 8-band GeoTIFF: B02,B03,B04,B08,B11,B12,B05,SCL.")
            if src.width * src.height > 1_000_000:
                raise ValueError("Crop your raster to at most one million pixels.")
            data = src.read().astype(np.float32)
            valid = (src.read_masks()[:7] > 0).all(axis=0)
            data[:7] *= scale
            data[:7, ~valid] = np.nan
            if src.crs is None:
                raise ValueError("The GeoTIFF must have a projected CRS.")
            finite = data[:7][np.isfinite(data[:7])]
            if finite.size == 0 or np.percentile(finite, 99) > 1.5:
                raise ValueError("Reflectance is not scaled correctly. Convert to surface reflectance first.")
            return Scene(data, src.transform, str(src.crs), {
                "id": name, "datetime": date, "source": "User-supplied GeoTIFF",
                "quality": "SCL supplied by user", "reflectance_scale": scale,
            })
