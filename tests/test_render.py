"""JSON 지오메트리 → SVG 렌더 테스트."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import attogrid                # noqa: E402
from attogrid import render    # noqa: E402

FAKE = {"OBJECTS": [
    {"entity": "LINE", "entmode": 2, "start": [0, 0, 0], "end": [10, 0, 0]},
    {"entity": "LINE", "entmode": 2, "start": [10, 0, 0], "end": [10, 5, 0]},
    {"entity": "CIRCLE", "entmode": 2, "center": [5, 2, 0], "radius": 1.0},
    {"entity": "LINE", "entmode": 0, "start": [999, 999, 0], "end": [1000, 1000, 0]},
]}


def _draw():
    return attogrid.Drawing(source=Path("x"), data=FAKE, objects=FAKE["OBJECTS"])


def test_json_to_svg_basic():
    svg = render.json_to_svg(_draw())
    assert "<svg" in svg and "viewBox" in svg
    assert svg.count("<polyline") == 3   # 모델공간 LINE 2 + CIRCLE 1


def test_model_only_excludes_block_defs():
    # entmode 0(블록정의)는 제외되어 1000,1000 좌표가 viewBox에 영향 없어야 함
    svg = render.json_to_svg(_draw())
    import re
    vb = re.search(r'viewBox="([^"]+)"', svg).group(1).split()
    w = float(vb[2])
    assert w < 100   # 도면 폭은 ~10, 블록정의(1000) 미포함


if __name__ == "__main__":
    test_json_to_svg_basic()
    test_model_only_excludes_block_defs()
    print("PASS render 테스트")
