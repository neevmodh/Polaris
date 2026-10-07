"""Cache real Sentinel-2 acquisitions and Hansen labels for an offline jury demo."""
import argparse
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor.catalog import PRESETS, fetch_pair, hansen_reference
from monitor.scenes import utm_grid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", choices=["forest", "lake", "all"], default="all")
    args = parser.parse_args()
    for kind in (["forest", "lake"] if args.preset == "all" else [args.preset]):
        p = PRESETS[kind]
        dest = ROOT / "data" / kind
        scenes = fetch_pair(p["bbox"], p["before"], p["after"], dest, log=lambda s: print(s, flush=True))
        for label, scene in zip(["before", "after"], scenes):
            scene.metadata["region"] = p["name"]
            scene.save(dest / f"{label}.npz")
        (dest / "preset.json").write_text(json.dumps(p, indent=2))
        if kind == "forest":
            hansen_reference(p["bbox"], utm_grid(p["bbox"]), dest, log=lambda s: print(s, flush=True))
        print(f"Cached {p['name']} at {dest}", flush=True)


if __name__ == "__main__":
    main()
