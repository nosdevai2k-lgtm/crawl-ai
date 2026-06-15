"""search: build_index (PIL) + search_images presets."""

import json
from pathlib import Path

import pytest

from src.search import build_index, search_images, PRESETS

PIL = pytest.importorskip("PIL")
from PIL import Image


def _mk(p: Path, w: int, h: int) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (10, 120, 90)).save(p)


@pytest.fixture()
def idx(tmp_path: Path):
    base = tmp_path / "images"
    _mk(base / "vinh_ha_long" / "vinh_ha_long_001.jpg", 1920, 1080)   # ngang
    _mk(base / "vinh_ha_long" / "vinh_ha_long_002.jpg", 600, 900)     # dọc
    _mk(base / "chua_mot_cot" / "chua_mot_cot_001.jpg", 1280, 720)
    (base / "names.json").write_text(json.dumps({
        "vinh_ha_long": "Vịnh Hạ Long Quảng Ninh Ha Long Bay",
        "chua_mot_cot": "Chùa Một Cột Hà Nội One Pillar Pagoda",
    }, ensure_ascii=False), encoding="utf-8")
    return build_index(base, save=False)


def test_build_index_reads_dimensions(idx) -> None:
    assert set(idx) == {"vinh_ha_long", "chua_mot_cot"}
    assert idx["vinh_ha_long"]["count"] == 2
    w = {(im["w"], im["h"]) for im in idx["vinh_ha_long"]["images"]}
    assert (1920, 1080) in w


def test_phong_canh_prefers_landscape(idx) -> None:
    r = search_images("ha long", "phong_canh", index=idx, top_k=10)
    res = [x for x in r["results"] if x["slug"] == "vinh_ha_long"]
    assert res and res[0]["w"] > res[0]["h"]  # ảnh ngang xếp trên


def test_di_tich_only_architecture(idx) -> None:
    r = search_images("ha noi", "di_tich", index=idx, top_k=10)
    slugs = {x["slug"] for x in r["results"]}
    assert "chua_mot_cot" in slugs
    assert "vinh_ha_long" not in slugs  # không phải kiến trúc -> loại


def test_location_tool_filters(idx) -> None:
    r = search_images("", "dia_diem", tools={"location": "quang ninh"}, index=idx, top_k=10)
    assert {x["slug"] for x in r["results"]} == {"vinh_ha_long"}


def test_request_body_shape(idx) -> None:
    r = search_images("dao", "tong_hop", index=idx, top_k=5)
    assert r["request"]["preset"] == "tong_hop"
    assert r["request"]["top_k"] == 5
    assert "tong_hop" in PRESETS



def test_nested_group_index_and_presets(tmp_path: Path) -> None:
    base = tmp_path / "images"
    _mk(base / "human" / "ho_chi_minh" / "ho_chi_minh_001.jpg", 600, 900)
    _mk(base / "festival" / "tet_trung_thu" / "tet_trung_thu_001.jpg", 1280, 720)
    _mk(base / "events" / "nha_giao" / "nha_giao_001.jpg", 1024, 768)
    _mk(base / "holidays" / "quoc_khanh" / "quoc_khanh_001.jpg", 800, 600)
    idx = build_index(base, save=False)
    assert set(idx) == {
        "human/ho_chi_minh",
        "festival/tet_trung_thu",
        "events/nha_giao",
        "holidays/quoc_khanh",
    }
    assert idx["human/ho_chi_minh"]["group"] == "human"

    # nhan_vat chỉ trả nhóm human
    r = search_images("ho chi minh", "nhan_vat", index=idx, top_k=10)
    assert {x["slug"] for x in r["results"]} == {"human/ho_chi_minh"}

    # le_su_kien gộp festival + events + holidays; loại human
    r2 = search_images("trung thu", "le_su_kien", index=idx, top_k=10)
    assert {x["slug"] for x in r2["results"]} == {"festival/tet_trung_thu"}

    r3 = search_images("", "le_su_kien", index=idx, top_k=10)
    assert {x["group"] for x in r3["results"]} == {"events", "festival", "holidays"}
    assert "human/ho_chi_minh" not in {x["slug"] for x in r3["results"]}

    # alias cũ su_kien / le_tet vẫn map về le_su_kien
    r4 = search_images("nha giao", "su_kien", index=idx, top_k=10)
    assert {x["slug"] for x in r4["results"]} == {"events/nha_giao"}
    assert r4["request"]["preset"] == "le_su_kien"  # alias su_kien → le_su_kien

    r5 = search_images("quoc khanh", "le_tet", index=idx, top_k=10)
    assert {x["slug"] for x in r5["results"]} == {"holidays/quoc_khanh"}
