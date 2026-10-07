"""Hourly weather from the Open-Meteo archive (ERA5 reanalysis, free, no key), cached on disk.
ERA5 is HISTORICAL reanalysis, not a weather forecast: an operational system would need an NWP forecast feed."""
from pathlib import Path
import time
import pandas as pd
import requests

CACHE = Path(__file__).resolve().parents[1] / "data" / "weather"
URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_year(lat: float, lon: float, year: int) -> pd.DataFrame:
    params = dict(latitude=lat, longitude=lon, start_date=f"{year}-01-01", end_date=f"{year}-12-31",
                  hourly="temperature_2m,shortwave_radiation,wind_speed_100m", timezone="UTC", wind_speed_unit="ms")
    for attempt in range(5):                       # the free archive occasionally answers 500/429; back off and retry
        r = requests.get(URL, params=params, timeout=120)
        if r.status_code < 500 and r.status_code != 429:
            break
        time.sleep(4 * (attempt + 1))
    r.raise_for_status()
    h = r.json()["hourly"]
    df = pd.DataFrame({"t2m": h["temperature_2m"], "ghi": h["shortwave_radiation"], "wind100": h["wind_speed_100m"]},
                      index=pd.to_datetime(h["time"]))
    return df


def load_weather(profile, years=range(2020, 2026), refresh=False) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{profile.key}_{years[0]}_{years[-1]}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    frames = []
    for y in years:                                # one cache file per year, so an interrupted download resumes
        f = CACHE / f"{profile.key}_{y}.parquet"
        if not f.exists() or refresh:
            fetch_year(profile.lat, profile.lon, y).to_parquet(f)
        frames.append(pd.read_parquet(f))
    df = pd.concat(frames)
    df = df[~df.index.duplicated()].sort_index()
    if df.isna().mean().max() > 0.01:
        raise ValueError("Too many missing weather values returned by the archive.")
    df = df.interpolate(limit=6).bfill().ffill()
    df.attrs["source"] = "Open-Meteo archive (ERA5 reanalysis)"
    df.to_parquet(path)
    return df
