"""Add one real intermediate acquisition to each cached case study."""
from pathlib import Path
import sys
from rasterio.warp import transform_bounds

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor.scenes import Scene
from monitor.catalog import search, fetch_scene
from monitor.workspace import timeline_key

if __name__ == "__main__":
    for kind, start, end in [("forest", "2021-07-01", "2021-09-30"),
                             ("lake", "2022-02-01", "2022-03-31")]:
        before = Scene.load(ROOT / "data" / kind / "before.npz")
        key = timeline_key(before, kind)
        folder = ROOT / "data" / "timeline" / key
        if any(folder.glob("*.npz")):
            print(f"{kind}: intermediate observation already cached", flush=True)
            continue
        bbox = list(transform_bounds(before.crs, "EPSG:4326", *before.bounds))
        grid = before.crs, before.transform, before.shape[1], before.shape[0]
        for item in search(bbox, start, end)[:3]:
            candidate = fetch_scene(item, grid, log=lambda msg: print(msg, flush=True))
            if candidate.valid.mean() >= .7:
                candidate.metadata["region"] = before.metadata.get("region", kind)
                candidate.save(folder / f"{candidate.metadata['datetime'][:10]}.npz")
                print(f"{kind}: cached {candidate.metadata['id']}", flush=True)
                break
        else:
            raise RuntimeError(f"{kind}: no sufficiently clear intermediate scene")
