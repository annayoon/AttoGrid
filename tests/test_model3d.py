"""2D→3D 압출 테스트."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import attogrid   # noqa: E402

# 모델공간 닫힌 사각형 2개 + 블록정의 1개(제외) + 큰 좌표
FAKE = {"OBJECTS": [
    {"entity": "LWPOLYLINE", "entmode": 2, "flag": 1,
     "points": [[1000, 1000], [1010, 1000], [1010, 1005], [1000, 1005]]},
    {"entity": "LWPOLYLINE", "entmode": 2, "flag": 1,
     "points": [[1020, 1000], [1030, 1000], [1030, 1005], [1020, 1005]]},
    {"entity": "LWPOLYLINE", "entmode": 0, "flag": 1,       # 블록정의 → 제외
     "points": [[0, 0], [1, 0], [1, 1], [0, 1]]},
    {"entity": "LINE", "entmode": 2, "start": [0, 0, 0], "end": [1, 1, 0]},  # 선 → 제외
]}


def _draw():
    return attogrid.Drawing(source=Path("x"), data=FAKE, objects=FAKE["OBJECTS"])


def test_extrude_counts_only_model_polygons():
    m = attogrid.extrude(_draw())
    assert m["count"] == 2          # 모델공간 사각형 2개만
    assert m["height"] > 0


def test_extrude_normalizes_coords():
    m = attogrid.extrude(_draw(), target_size=100.0)
    xs = [p[0] for fp in m["footprints"] for p in fp]
    ys = [p[1] for fp in m["footprints"] for p in fp]
    # 중심 원점, 최대 변 ~100 → 좌표는 ±50 안
    assert max(abs(min(xs)), abs(max(xs))) <= 51
    assert max(abs(min(ys)), abs(max(ys))) <= 51


if __name__ == "__main__":
    test_extrude_counts_only_model_polygons()
    test_extrude_normalizes_coords()
    print("PASS model3d 테스트")
