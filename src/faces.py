"""Face detection + embeddings via OpenCV (YuNet detector + SFace recogniser).

Pure-wheel, no compilation: works on Python 3.14 where insightface has no wheel.
Everything degrades gracefully — if opencv or the ONNX models are missing,
`available()` is False and callers should skip biometric features.

Models (downloaded to data/models/):
  face_detection_yunet_2023mar.onnx     YuNet face detector
  face_recognition_sface_2021dec.onnx   SFace 128-d embedding

SFace cosine similarity: higher = more similar; ~0.363 is OpenCV's default
same-person threshold.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

SFACE_COSINE_THRESHOLD = 0.363

_MODELS_DIR = Path("data/models")
_DET_MODEL = "face_detection_yunet_2023mar.onnx"
_REC_MODEL = "face_recognition_sface_2021dec.onnx"

_IMG_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

_det = None  # cached cv2.FaceDetectorYN
_rec = None  # cached cv2.FaceRecognizerSF
_cv2 = None


def _import_cv2():
    global _cv2
    if _cv2 is None:
        try:
            import cv2  # type: ignore
            _cv2 = cv2
        except Exception:
            _cv2 = False
    return _cv2 or None


def models_present() -> bool:
    return (_MODELS_DIR / _DET_MODEL).is_file() and (_MODELS_DIR / _REC_MODEL).is_file()


def available() -> bool:
    """True if opencv is importable AND both ONNX models exist."""
    return _import_cv2() is not None and models_present()


def _detector():
    global _det
    if _det is None:
        cv2 = _import_cv2()
        _det = cv2.FaceDetectorYN.create(
            str(_MODELS_DIR / _DET_MODEL), "", (320, 320),
            score_threshold=0.7, nms_threshold=0.3, top_k=5000,
        )
    return _det


def _recogniser():
    global _rec
    if _rec is None:
        cv2 = _import_cv2()
        _rec = cv2.FaceRecognizerSF.create(str(_MODELS_DIR / _REC_MODEL), "")
    return _rec


def _decode(image_bytes: bytes):
    cv2 = _import_cv2()
    if cv2 is None:
        return None
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def detect_faces(image_bytes: bytes) -> list[dict[str, Any]]:
    """Detect faces. Returns a list of {box:(x,y,w,h), score, row} sorted by area."""
    if not available():
        return []
    img = _decode(image_bytes)
    if img is None or img.size == 0:
        return []
    h, w = img.shape[:2]
    det = _detector()
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    out: list[dict[str, Any]] = []
    if faces is None:
        return out
    for row in faces:
        x, y, fw, fh = (float(v) for v in row[:4])
        out.append({"box": (x, y, fw, fh), "score": float(row[-1]), "row": row, "area": fw * fh})
    out.sort(key=lambda f: f["area"], reverse=True)
    return out


def embed_largest_face(image_bytes: bytes):
    """128-d L2-normalised embedding of the largest face, or None."""
    if not available():
        return None
    img = _decode(image_bytes)
    if img is None or img.size == 0:
        return None
    h, w = img.shape[:2]
    det = _detector()
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    if faces is None or len(faces) == 0:
        return None
    # largest face
    row = max(faces, key=lambda r: float(r[2]) * float(r[3]))
    rec = _recogniser()
    aligned = rec.alignCrop(img, row)
    feat = rec.feature(aligned).flatten().astype(np.float32)
    n = np.linalg.norm(feat)
    return feat / n if n else feat


def cosine(a, b) -> float:
    if a is None or b is None:
        return 0.0
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if not na or not nb:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _iter_images(folder: Path):
    if not folder.is_dir():
        return
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() in _IMG_SUFFIXES and f.is_file():
            yield f


def folder_face_embeddings(folder: Path) -> dict[str, Any]:
    """Embed the largest face of every image in a folder.

    Returns {items:[(path, emb)], no_face:[paths], total:int}."""
    items: list[tuple[Path, Any]] = []
    no_face: list[Path] = []
    total = 0
    for f in _iter_images(folder):
        total += 1
        try:
            emb = embed_largest_face(f.read_bytes())
        except Exception:
            emb = None
        if emb is None:
            no_face.append(f)
        else:
            items.append((f, emb))
    return {"items": items, "no_face": no_face, "total": total}


def reference_embedding(embeddings: list, *, threshold: float = 0.3) -> Any:
    """Robust centroid of a person's face embeddings: mean, drop outliers below
    `threshold` cosine to the mean, then re-average. Returns the normalised
    reference vector, or None."""
    embs = [np.asarray(e, dtype=np.float32) for e in embeddings if e is not None]
    if not embs:
        return None
    mean = np.mean(embs, axis=0)
    kept = [e for e in embs if cosine(e, mean) >= threshold]
    if kept:
        mean = np.mean(kept, axis=0)
    n = np.linalg.norm(mean)
    return mean / n if n else mean


def clean_folder(
    folder: Path,
    *,
    threshold: float = SFACE_COSINE_THRESHOLD,
    move_rejects: bool = False,
) -> dict[str, Any]:
    """Verify a harvested face folder against its own reference face. Flags
    images with no face or an inconsistent face (wrong person / group photo).
    With move_rejects, moves them into a `_rejected/` subfolder.

    Returns {total, kept, rejected:[(name,reason,score)], reference: bool}."""
    fe = folder_face_embeddings(folder)
    ref = reference_embedding([e for _, e in fe["items"]])
    rejected: list[tuple[str, str, float]] = []
    kept = 0
    if ref is None:
        return {"total": fe["total"], "kept": 0,
                "rejected": [(p.name, "no_face", 0.0) for p in fe["no_face"]],
                "reference": False}
    reject_dir = folder / "_rejected"
    for p in fe["no_face"]:
        rejected.append((p.name, "no_face", 0.0))
    for p, emb in fe["items"]:
        s = cosine(emb, ref)
        if s < threshold:
            rejected.append((p.name, "wrong_person", round(s, 3)))
        else:
            kept += 1
    if move_rejects and rejected:
        reject_dir.mkdir(exist_ok=True)
        names = {r[0] for r in rejected}
        for p in _iter_images(folder):
            if p.name in names:
                p.replace(reject_dir / p.name)
        for p in fe["no_face"]:
            if p.exists():
                p.replace(reject_dir / p.name)
    return {"total": fe["total"], "kept": kept, "rejected": rejected, "reference": True}


def build_references(images_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Reference face embedding per harvested person folder under human/.

    Returns {slug: {"name": display, "emb": vec, "n": face_count}}."""
    images_root = images_root or Path("data/images")
    human = images_root / "human"
    refs: dict[str, dict[str, Any]] = {}
    if not human.is_dir():
        return refs
    import json
    names: dict[str, str] = {}
    nf = images_root / "names.json"
    if nf.is_file():
        try:
            names = json.loads(nf.read_text(encoding="utf-8"))
        except Exception:
            names = {}
    for folder in sorted(p for p in human.iterdir() if p.is_dir()):
        if folder.name == "_rejected":
            continue
        fe = folder_face_embeddings(folder)
        ref = reference_embedding([e for _, e in fe["items"]])
        if ref is None:
            continue
        display = names.get(f"human/{folder.name}") or folder.name
        refs[folder.name] = {"name": display, "emb": ref, "n": len(fe["items"])}
    return refs


def identify(image_bytes: bytes, references: dict[str, dict[str, Any]], *,
             min_score: float = SFACE_COSINE_THRESHOLD) -> dict[str, Any] | None:
    """Identify the largest face in an image against reference embeddings.
    Returns {slug, name, score} of the best match above min_score, else None."""
    emb = embed_largest_face(image_bytes)
    if emb is None or not references:
        return None
    best_slug, best_score = None, -1.0
    for slug, info in references.items():
        s = cosine(emb, info["emb"])
        if s > best_score:
            best_slug, best_score = slug, s
    if best_slug is None or best_score < min_score:
        return None
    return {"slug": best_slug, "name": references[best_slug]["name"], "score": round(best_score, 3)}
