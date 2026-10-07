"""Spectral screening indices, adapted from TerraVision and waterquality.

Water ratios are unitless Sentinel-2 band approximations, not pollutant concentrations.
See THIRD_PARTY_NOTICES.md for original sources, wavelengths and changes.
"""
import numpy as np
from .scenes import assert_aligned


def ratio(a, b):
    out = np.full(np.shape(a), np.nan, dtype=np.float32)
    np.divide(a, b, out=out, where=np.isfinite(a) & np.isfinite(b) & (np.abs(b) > 1e-6))
    return out


def normalized(a, b):
    return ratio(a - b, a + b)


def indices(scene):
    b = scene.band
    out = {"NDVI": normalized(b("nir"), b("red")), "NBR": normalized(b("nir"), b("swir22")),
           "NDMI": normalized(b("nir"), b("swir16")), "NDWI": normalized(b("green"), b("nir")),
           "MNDWI": normalized(b("green"), b("swir16")),
           "NDCI": normalized(b("rededge1"), b("red")),
           "NDTI": normalized(b("red"), b("green")),
           "visible_turbidity_ratio": ratio(b("red") + b("green"), b("blue"))}
    for key, arr in out.items():
        out[key] = np.where(scene.valid, arr, np.nan)
    return out


def forest_screen(before, after, drop=0.2, vegetation=0.6, min_pixels=4):
    from scipy.ndimage import label
    assert_aligned(before, after)
    ib, ia = indices(before), indices(after)
    valid = before.valid & after.valid
    eligible = valid & (ib["NDVI"] >= vegetation)
    delta = ia["NDVI"] - ib["NDVI"]
    loss = eligible & (delta < -drop)
    groups, _ = label(loss)
    sizes = np.bincount(groups.ravel())
    keep = sizes >= min_pixels
    keep[0] = False
    loss = keep[groups]
    return {"loss": loss, "valid": valid, "eligible": eligible,
            "delta": np.where(valid, delta, np.nan), "before": ib, "after": ia}


def water_screen(scene, mndwi=0.0):
    from scipy.ndimage import binary_erosion
    i = indices(scene)
    # Restrict to open water; vegetated floating mats are not treated as pure water.
    water = scene.valid & ((scene.band("scl") == 6) | ((i["MNDWI"] > mndwi) & (i["NDVI"] < 0.2)))
    # border_value=1: the scene edge is not a shoreline, so water touching it is kept
    water = binary_erosion(water, iterations=1, border_value=1)
    return {"water": water, **{k: np.where(water, v, np.nan) for k, v in i.items()}}
