"""Network-independent world geometry and validated station navigation."""
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]

def project(longitude, latitude):
    lon, lat = float(longitude), float(latitude)
    if not math.isfinite(lon) or not math.isfinite(lat) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError("Coordinates require latitude -90…90 and longitude -180…180.")
    return (lon + 180) * 1000 / 360, (90 - lat) * 500 / 180

def world_paths():
    world = json.loads((ROOT / "assets/world.geojson").read_text())
    paths = []
    for feature in world["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            pieces = []
            for ring in polygon:
                points = [project(lon, lat) for lon, lat, *_ in ring]
                pieces.append("M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in points) + "Z")
            paths.append(" ".join(pieces))
    return paths

def selected_station(event, entries, gas):
    """Only accepted forecast sites may change widget state."""
    if not isinstance(event, dict) or event.get("gas") != gas:
        return None
    return next((e["station"] for e in entries if e["gas"] == gas and e["eligible"]
                 and e["station"] == event.get("station")), None)
