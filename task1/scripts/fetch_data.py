"""Fetch public NOAA CC0 daily observations and preserve provenance."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def download(pair):
    gas, station = pair
    name = f"{gas}_{station}_surface-insitu_1_ccgg_DailyData.txt"
    url = f"https://gml.noaa.gov/aftp/data/trace_gases/{gas}/in-situ/surface/txt/{name}"
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    if not response.text.startswith("# header_lines"):
        raise ValueError(f"Not a NOAA data file: {url}")
    (ROOT / "data/raw" / name).write_bytes(response.content)
    entry = {"gas": gas, "station": station.upper(), "url": url,
             "file": f"data/raw/{name}", "sha256": sha256(response.content).hexdigest(),
             "retrieved_at": datetime.now(timezone.utc).isoformat()}
    print(f"Downloaded {gas.upper()} / {station.upper()} ({len(response.content):,} bytes)", flush=True)
    return entry

if __name__ == "__main__":
    pairs = [(gas, station) for gas in ("co2", "ch4") for station in ("mlo", "brw", "smo")]
    pairs.append(("co2", "spo"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifest = list(pool.map(download, pairs))
    (ROOT / "data/manifest.json").write_text(json.dumps(manifest, indent=2))
