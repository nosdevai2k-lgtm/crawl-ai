"""Face embedding helpers. Pure-logic tests run everywhere; detection tests
skip gracefully when opencv / ONNX models are absent."""

from __future__ import annotations

import numpy as np

from src import faces


def test_cosine_basic() -> None:
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert faces.cosine(a, b) == 1.0
    assert abs(faces.cosine(a, c)) < 1e-6
    assert faces.cosine(a, None) == 0.0


def test_reference_embedding_drops_outlier() -> None:
    # five near-identical vectors + one opposite outlier
    base = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    embs = [base + np.array([0, 0.01 * i, 0], dtype=np.float32) for i in range(5)]
    embs.append(np.array([-1.0, 0.0, 0.0], dtype=np.float32))  # outlier
    ref = faces.reference_embedding(embs, threshold=0.3)
    assert faces.cosine(ref, base) > 0.95  # outlier excluded -> ref ~ base
    assert np.isclose(np.linalg.norm(ref), 1.0, atol=1e-5)


def test_reference_embedding_empty() -> None:
    assert faces.reference_embedding([]) is None
    assert faces.reference_embedding([None, None]) is None


def test_identify_picks_best_match(monkeypatch) -> None:
    # bypass opencv: feed a known query embedding and reference vectors
    q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    monkeypatch.setattr(faces, "available", lambda: True)
    monkeypatch.setattr(faces, "embed_largest_face", lambda b: q)
    refs = {
        "alice": {"name": "Alice", "emb": np.array([0.9, 0.1, 0.0], dtype=np.float32), "n": 5},
        "bob": {"name": "Bob", "emb": np.array([0.0, 1.0, 0.0], dtype=np.float32), "n": 5},
    }
    res = faces.identify(b"x", refs, min_score=0.3)
    assert res is not None and res["slug"] == "alice"
    # raising the bar above the best score -> no match
    assert faces.identify(b"x", refs, min_score=0.999) is None


def test_identify_no_references(monkeypatch) -> None:
    monkeypatch.setattr(faces, "available", lambda: True)
    monkeypatch.setattr(faces, "embed_largest_face", lambda b: np.array([1.0, 0.0], dtype=np.float32))
    assert faces.identify(b"x", {}) is None
