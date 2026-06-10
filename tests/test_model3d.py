"""2D→3D 압출 테스트."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import attogrid   # noqa: E402

# 모델공간 사각형 2개(크기 다름) + 블록정의 1개(제외)
FAKE = {"OBJECTS": [
    # 작은 랙 (area 작음)
    {"entity": "LWPOLYLINE", "entmode": 2, "flag": 1,
     "points": [[1000, 1000], [1010, 1000], [1010, 1005], [1000, 1005]]},
    # 더 작은 랙
    {"entity": "LWPOLYLINE", "entmode": 2, "flag": 1,
     "points": [[1020, 1000], [1030, 1000], [1030, 1005], [1020, 1005]]},
    # 블록정의(entmode=0) → 제외
    {"entity": "LWPOLYLINE", "entmode": 0, "flag": 1,
     "points": [[0, 0], [1, 0], [1, 1], [0, 1]]},
    # LINE → 제외
    {"entity": "LINE", "entmode": 2, "start": [0, 0, 0], "end": [1, 1, 0]},
]}


def _draw():
    return attogrid.Drawing(source=Path("x"), data=FAKE, objects=FAKE["OBJECTS"])


def test_extrude_counts_only_model_polygons():
    m = attogrid.extrude(_draw())
    assert m["count"] == 2, f"expected 2, got {m['count']}"
    assert m["base_height"] > 0
    assert "type_counts" in m


def test_extrude_normalizes_coords():
    m = attogrid.extrude(_draw(), target_size=100.0)
    xs = [p[0] for obj in m["objects"] for p in obj["points"]]
    ys = [p[1] for obj in m["objects"] for p in obj["points"]]
    # 중심 원점, 최대 변 ~100 → 좌표는 ±51 안
    assert max(abs(min(xs)), abs(max(xs))) <= 51
    assert max(abs(min(ys)), abs(max(ys))) <= 51


def test_extrude_has_type_and_layer():
    m = attogrid.extrude(_draw())
    for obj in m["objects"]:
        assert obj["type"] in ("rack", "equipment", "zone")
        assert "layer" in obj
        assert "area_norm" in obj


if __name__ == "__main__":
    test_extrude_counts_only_model_polygons()
    test_extrude_normalizes_coords()
    test_extrude_has_type_and_layer()
    print("PASS model3d 테스트")
