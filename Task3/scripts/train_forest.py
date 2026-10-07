import sys
from pathlib import Path
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor.scenes import Scene
from monitor.learning import train

if __name__ == "__main__":
    path = ROOT / "data" / "forest"
    if not (path / "reference.npz").exists():
        raise SystemExit("Run: python scripts/bootstrap_data.py --preset forest")
    before, after = Scene.load(path / "before.npz"), Scene.load(path / "after.npz")
    with np.load(path / "reference.npz", allow_pickle=False) as z:
        reference = {k: z[k] for k in z.files}
    _, metrics = train(before, after, reference, ROOT / "models")
    print(json.dumps(metrics, indent=2))
