"""도면 구획 분할 테스트."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import attogrid          # noqa: E402

# 좌우로 떨어진 두 시트(각각 큰 사각형 프레임 + 내부 선)
def _rect(x0, y0, x1, y1):
    return {"entity": "LWPOLYLINE", "entmode": 2, "flag": 1,
            "points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}

OBJ = []
# 시트 A (0~100), 시트 B (300~400) — 큰 프레임 + 내부 도형
for ox in (0, 300):
    OBJ.append(_rect(ox, 0, ox + 100, 150))            # 프레임
    OBJ.append({"entity": "LINE", "entmode": 2,
                "start": [ox + 20, 20, 0], "end": [ox + 80, 20, 0]})
    OBJ.append(_rect(ox + 10, 40, ox + 60, 90))        # 내부 사각형


def _draw():
    data = {"OBJECTS": OBJ}
    return attogrid.Drawing(source=Path("x"), data=data, objects=OBJ)


def test_partition_cluster_splits_two():
    secs = attogrid.partition(_draw(), method="cluster", gap_ratio=0.1)
    assert len(secs) == 2
    assert all(s["count"] > 0 for s in secs)


def test_partition_grid():
    secs = attogrid.partition(_draw(), method="grid", rows=1, cols=2)
    assert len(secs) == 2


def test_partition_frame_detects_two_sheets():
    secs = attogrid.partition(_draw(), method="frame")
    assert len(secs) == 2


def test_section_title_picks_largest_text():
    from attogrid.partition import section_title
    data = {"OBJECTS": [
        {"entity": "TEXT", "text_value": "작은글씨", "ins_pt": [50, 50, 0], "height": 5},
        {"entity": "TEXT", "text_value": "전력계통도", "ins_pt": [50, 60, 0], "height": 40},
        {"entity": "TEXT", "text_value": "ABC-123", "ins_pt": [50, 70, 0], "height": 99},  # 식별자 제외
    ]}
    d = attogrid.Drawing(source=Path("x"), data=data, objects=data["OBJECTS"])
    assert section_title(d, (0, 0, 100, 100)) == "전력계통도"


def test_render_bounds_clips():
    from attogrid import render
    # 시트 A 영역만 렌더 → 시트 B 도형 제외
    secs = attogrid.partition(_draw(), method="frame")
    a = secs[0]
    svg = render.json_to_svg(_draw(), bounds=tuple(a["bounds"]))
    assert "<polyline" in svg


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("partition 테스트 통과")
