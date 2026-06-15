"""Download the OpenCV face models (YuNet detector + SFace recogniser).

These power src/faces.py (face detection / embeddings / identify). They are not
committed (≈37 MB). Run once:

    python scripts/download_face_models.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

_BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
_FILES = {
    "face_detection_yunet_2023mar.onnx":
        f"{_BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx":
        f"{_BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}


def main() -> None:
    out_dir = Path("data/models")
    out_dir.mkdir(parents=True, exist_ok=True)
    for fn, url in _FILES.items():
        dest = out_dir / fn
        if dest.exists() and dest.stat().st_size > 10_000:
            print(f"exists: {fn} ({dest.stat().st_size} bytes)")
            continue
        print(f"downloading {fn} …")
        urllib.request.urlretrieve(url, dest)
        print(f"  saved {dest.stat().st_size} bytes")
    print("done.")


if __name__ == "__main__":
    main()
