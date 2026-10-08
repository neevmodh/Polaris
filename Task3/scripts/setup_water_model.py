"""Download upstream U-Net weights with size/SHA256 verification from Git LFS pointer."""
from pathlib import Path
import hashlib
import requests

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    repo = ROOT / "references" / "lake-detection-water-quality"
    filename = "best_water_segmentation_model_unet.pth"
    pointer = (repo / "models" / filename).read_text(encoding="utf-8")
    checksum = next(s.split(":", 1)[1] for s in pointer.splitlines() if s.startswith("oid sha256:"))
    size = int(next(s.split()[1] for s in pointer.splitlines() if s.startswith("size ")))
    import subprocess
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    url = f"https://media.githubusercontent.com/media/Iulia-plesu/lake-detection-water-quality/{sha}/models/{filename}"
    dest = ROOT / "models" / "water_unet.pth"
    dest.parent.mkdir(exist_ok=True)
    temp = dest.with_suffix(".part")
    digest = hashlib.sha256()
    with requests.get(url, stream=True, timeout=(15, 90)) as response:
        response.raise_for_status()
        with temp.open("wb") as f:
            for block in response.iter_content(1024 * 1024):
                f.write(block)
                digest.update(block)
    if temp.stat().st_size != size or digest.hexdigest() != checksum:
        temp.unlink(missing_ok=True)
        raise SystemExit("The model download failed its integrity check.")
    temp.replace(dest)
    print(f"Verified {dest}: {size} bytes, SHA256 {checksum}")
