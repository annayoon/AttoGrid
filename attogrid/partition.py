"""
도면 구획 분할.

세 가지 기준:
  - frame   : 시트 테두리(대형 사각형)로 분할 — 도면에 프레임이 있을 때 가장 정확
  - cluster : 엔티티 간 빈 간격(X→Y)으로 자동 분할 — 프레임 없는 도면에도 적용
  - grid    : 균등 격자(rows×cols)로 분할 — 내용과 무관
  - auto    : frame이 2개 이상이면 frame, 아니면 cluster
각 구획은 {"label", "bounds": (minx, miny, maxx, maxy), "count"}.
"""
from __future__ import annotations

from .render import _polylines, _dominant_cluster


def _bounds(pls):
    xs = [p[0] for pl in pls for p in pl]
    ys = [p[1] for pl in pls for p in pl]
    return (min(xs), min(ys), max(xs), max(ys))


def _centroid(pl):
    return (sum(p[0] for p in pl) / len(pl), sum(p[1] for p in pl) / len(pl))


def _overlap(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area_a = (a[2] - a[0]) * (a[3] - a[1]) or 1
    return inter / area_a


def detect_frames(pls, minx, miny, maxx, maxy):
    W, H = (maxx - minx) or 1, (maxy - miny) or 1
    cand = []
    for pl in pls:
        if 4 <= len(pl) <= 6:
            xs = [p[0] for p in pl]
            ys = [p[1] for p in pl]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if w > W * 0.12 and h > H * 0.12:
                cand.append((min(xs), min(ys), max(xs), max(ys)))
    uniq = []
    for f in sorted(cand, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1])):
        if not any(_overlap(f, u) > 0.5 or _overlap(u, f) > 0.5 for u in uniq):
            uniq.append(f)
    return sorted(uniq, key=lambda b: (round(b[0] / (W * 0.1)), b[1]))


def _split_axis(vals, span, gap_ratio):
    """정렬된 값들을 큰 간격 기준으로 그룹핑 → 각 그룹의 (min,max)."""
    vals = sorted(vals)
    thr = span * gap_ratio
    groups = [[vals[0]]]
    for v in vals[1:]:
        if v - groups[-1][-1] > thr:
            groups.append([v])
        else:
            groups[-1].append(v)
    return [(g[0], g[-1]) for g in groups]


def _pad(b, fx, fy):
    return (b[0] - fx, b[1] - fy, b[2] + fx, b[3] + fy)


def partition(drawing, method: str = "auto", rows: int = 2, cols: int = 2,
              gap_ratio: float = 0.02, max_count: int = 80000) -> list[dict]:
    pls = _dominant_cluster(_polylines(drawing.objects, max_count))
    if not pls:
        return []
    minx, miny, maxx, maxy = _bounds(pls)
    W, H = (maxx - minx) or 1, (maxy - miny) or 1

    if method == "auto":
        frames = detect_frames(pls, minx, miny, maxx, maxy)
        method = "frame" if len(frames) >= 2 else "cluster"

    sections = []
    if method == "frame":
        frames = detect_frames(pls, minx, miny, maxx, maxy)
        for i, f in enumerate(frames, 1):
            sections.append({"label": f"시트 {i}", "bounds": _pad(f, W * 0.01, H * 0.01)})

    elif method == "grid":
        for r in range(rows):
            for c in range(cols):
                b = (minx + W * c / cols, miny + H * (rows - 1 - r) / rows,
                     minx + W * (c + 1) / cols, miny + H * (rows - r) / rows)
                sections.append({"label": f"R{r + 1}C{c + 1}", "bounds": b})

    else:  # cluster: 빈 간격이 더 뚜렷한 축으로 분할(과분할 방지)
        cents = [_centroid(pl) for pl in pls]
        xg = _split_axis([c[0] for c in cents], W, gap_ratio)
        yg = _split_axis([c[1] for c in cents], H, gap_ratio)
        # 그룹 수가 2~10이고 더 많이 나뉘는 축을 선택
        use_x = (2 <= len(xg) <= 10) and len(xg) >= len(yg)
        ranges = xg if use_x else yg
        axis = 0 if use_x else 1
        for i, (lo, hi) in enumerate(ranges, 1):
            cell = [pl for pl, c in zip(pls, cents) if lo <= c[axis] <= hi]
            if cell:
                sections.append({"label": f"구획 {i}",
                                 "bounds": _pad(_bounds(cell), W * 0.01, H * 0.01)})

    # 각 폴리라인을 하나의 구획에만 배정해 개수 집계(겹치는 bounds 대응)
    for s in sections:
        s["count"] = 0
    for pl in pls:
        cx, cy = _centroid(pl)
        for s in sections:
            b = s["bounds"]
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                s["count"] += 1
                break
    for s in sections:
        s["bounds"] = [round(v, 2) for v in s["bounds"]]
    return [s for s in sections if s["count"] > 0]
