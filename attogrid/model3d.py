"""
2D → 3D 압출.

모델 공간의 닫힌 폴리라인(사각형 윤곽 등)을 푸트프린트로 추출하고,
좌표를 정규화(중심 이동 + 스케일)해 three.js에서 박스로 압출할 수 있게 한다.

주의: 전기 계통도라 '랙 평면 배치'가 명확치 않을 수 있다. 여기서는 닫힌 윤곽을
일괄 압출하는 일반적 방식을 제공한다. 실제 랙만 뽑으려면 레이어/블록 필터를 건다.
"""
from __future__ import annotations

from .render import _dominant_cluster


def _footprint_polys(objects, max_count, min_pts, max_pts):
    polys = []
    for o in objects:
        if o.get("entmode") != 2 or o.get("entity") != "LWPOLYLINE":
            continue
        pts = [(p[0], p[1]) for p in o.get("points", []) if len(p) >= 2]
        closed = bool(o.get("flag", 0) & 1)
        if min_pts <= len(pts) <= max_pts and (closed or len(pts) >= 4):
            polys.append(pts)
            if len(polys) >= max_count:
                break
    return polys


def extrude(drawing, max_count: int = 2500, min_pts: int = 4, max_pts: int = 8,
            target_size: float = 100.0, height_ratio: float = 0.04) -> dict:
    """닫힌 윤곽을 정규화된 푸트프린트 목록으로 반환.

    반환: {footprints: [[[x,y],...],...], height, count, span}
    좌표는 bbox 중심을 원점으로 옮기고 최대 변이 target_size가 되도록 스케일.
    """
    polys = _footprint_polys(drawing.objects, max_count, min_pts, max_pts)
    polys = _dominant_cluster(polys)
    if not polys:
        return {"footprints": [], "height": 1.0, "count": 0, "span": 0.0}

    xs = [p[0] for pl in polys for p in pl]
    ys = [p[1] for pl in polys for p in pl]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    span = max(maxx - minx, maxy - miny) or 1.0
    s = target_size / span

    footprints = [[[round((x - cx) * s, 3), round((y - cy) * s, 3)] for x, y in pl]
                  for pl in polys]
    return {
        "footprints": footprints,
        "height": round(target_size * height_ratio, 3),
        "count": len(footprints),
        "span": round(span, 1),
    }
