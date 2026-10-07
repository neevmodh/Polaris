"""Read NOAA observations and validate local daily sensor uploads."""
from pathlib import Path
from io import StringIO
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GASES = {"co2": {"name": "Carbon dioxide", "label": "CO₂", "unit": "ppm"},
         "ch4": {"name": "Methane", "label": "CH₄", "unit": "ppb"}}

def manifest():
    return json.loads((ROOT / "data/manifest.json").read_text())

def read_noaa(gas, station):
    entry = next(e for e in manifest() if e["gas"] == gas and e["station"] == station)
    path = ROOT / entry["file"]
    raw = path.read_text()
    metadata = {}
    for line in raw.splitlines():
        if line.startswith("# ") and ":" in line:
            key, val = line[2:].split(":", 1)
            metadata[key.strip()] = val.strip()
    frame = pd.read_csv(StringIO(raw), sep=r"\s+", comment="#")
    valid = (frame["value"] > 0) & (frame["nvalue"] > 0) & (frame["qcflag"] == "...")
    clean = pd.DataFrame({"date": pd.to_datetime(frame.loc[valid, "datetime"], utc=True).dt.tz_localize(None),
                          "value": frame.loc[valid, "value"].astype(float)})
    clean = clean.sort_values("date").reset_index(drop=True)
    info = {**entry, "name": metadata["site_name"], "latitude": float(metadata["site_latitude"]),
            "longitude": float(metadata["site_longitude"]), "elevation": float(metadata["site_elevation"]),
            "unit": GASES[gas]["unit"], "citation": metadata.get("dataset_citation", ""),
            "license": metadata.get("dataset_provider_license", ""),
            "release": metadata.get("dataset_creation_date", ""), "source_rows": len(frame),
            "rejected_rows": int((~valid).sum()), "origin": "NOAA GML baseline station"}
    return clean, info

def load_upload(content: bytes, gas: str):
    if len(content) > 10_000_000:
        raise ValueError("Use a CSV smaller than 10 MB.")
    try:
        frame = pd.read_csv(StringIO(content.decode("utf-8-sig")))
    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError("Upload a UTF-8 CSV with date,value columns.") from exc
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    if not {"date", "value"}.issubset(frame.columns):
        raise ValueError("The CSV must include date and value columns (daily mean concentration).")
    dates = pd.to_datetime(frame["date"], errors="coerce", utc=True)
    values = pd.to_numeric(frame["value"], errors="coerce")
    if dates.isna().any() or values.isna().any() or not np.isfinite(values).all():
        raise ValueError("Every row needs a valid date and a finite numeric value; remove invalid rows first.")
    if (values <= 0).any():
        raise ValueError("Concentrations must be positive; remove missing-value sentinels such as -999.99.")
    if "unit" in frame.columns:
        supplied = frame["unit"].astype(str).str.strip().str.lower()
        if not supplied.eq(GASES[gas]["unit"]).all():
            raise ValueError(f"This gas requires {GASES[gas]['unit']} units; convert the CSV before uploading.")
    daily = dates.dt.tz_localize(None).dt.normalize()
    if daily.duplicated().any():
        raise ValueError("Provide exactly one daily mean per UTC date. Aggregate hourly or duplicate readings first.")
    clean = pd.DataFrame({"date": daily, "value": values}).sort_values("date").reset_index(drop=True)
    if clean["date"].max().date() > pd.Timestamp.now(tz="UTC").date():
        raise ValueError("Observation dates cannot be in the future.")
    validate_series(clean)
    return clean

def validate_series(frame):
    span = (frame["date"].max() - frame["date"].min()).days + 1
    if len(frame) < 900 or span < 1095:
        raise ValueError("Training needs at least 900 valid daily observations spanning 3 years, including annual seasonality.")
    recent = frame[frame.date >= frame.date.max() - pd.Timedelta(days=7)]
    if len(recent) < 3:
        raise ValueError("At least 3 observations are needed in the last 7 days for a reliable forecast origin.")
    return {"count": len(frame), "span": span, "coverage": len(frame) / span,
            "first": frame.date.min(), "last": frame.date.max()}
