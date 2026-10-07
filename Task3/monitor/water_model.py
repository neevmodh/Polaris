"""Optional adapter for Iulia Plesu's Apache-2.0 U-Net architecture and weights.

Modifications: tiled CPU inference, valid-pixel normalization, safe state_dict loading,
overlap averaging, no upstream file writes, and exclusion of invalid pixels.
"""
import importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "models" / "water_unet.pth"


def available():
    return WEIGHTS.exists() and WEIGHTS.stat().st_size > 1_000_000 and importlib.util.find_spec("torch") is not None


def segment(scene):
    if not available():
        raise ValueError("Run scripts/setup_water_model.py and install requirements-water.txt first.")
    import torch
    torch.set_num_threads(2)
    source = ROOT / "references" / "lake-detection-water-quality" / "models.py"
    spec = importlib.util.spec_from_file_location("polaris_upstream_water_models", source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    model = mod.UNet(in_channels=6, num_classes=2)
    model.load_state_dict(torch.load(WEIGHTS, map_location="cpu", weights_only=True))
    model.eval()
    h, w = scene.shape
    # Follow upstream's band order and per-band min/max normalization.
    data = scene.data[:6].copy()
    for i in range(6):
        finite = np.isfinite(data[i]) & scene.valid
        if not finite.any():
            raise ValueError("Scene has no valid pixels for water inference.")
        lo, hi = data[i][finite].min(), data[i][finite].max()
        data[i] = np.where(finite, (data[i] - lo) / max(float(hi - lo), 1e-6), 0)
    tile, stride = 128, 96
    ph, pw = max(tile, int(np.ceil(h / 16)) * 16), max(tile, int(np.ceil(w / 16)) * 16)
    padded = np.pad(data, ((0, 0), (0, ph - h), (0, pw - w)), mode="edge")
    sums, counts = np.zeros((ph, pw)), np.zeros((ph, pw))
    ys = sorted(set(list(range(0, ph - tile + 1, stride)) + [ph - tile]))
    xs = sorted(set(list(range(0, pw - tile + 1, stride)) + [pw - tile]))
    with torch.inference_mode():
        for y in ys:
            for x in xs:
                block = torch.from_numpy(padded[:, y:y+tile, x:x+tile]).unsqueeze(0).float()
                p = torch.softmax(model(block), dim=1)[0, 1].numpy()
                sums[y:y+tile, x:x+tile] += p
                counts[y:y+tile, x:x+tile] += 1
    return (sums[:h, :w] / counts[:h, :w] > 0.5) & scene.valid
