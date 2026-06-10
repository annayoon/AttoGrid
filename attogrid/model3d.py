"""
2D → 3D 압출.

닫힌 폴리라인을 면적 기반으로 분류(zone / equipment / rack)하고
레이어 이름·ACI 색상도 함께 반환해 three.js에서 높이·색상을 다르게 표현한다.

zone      : 큰 구역 경계 (방, 섹션) — 얇은 슬라브
equipment : 중간 장비 (PDU, ATS, 분전반) — 중간 높이
rack      : 작은 랙/기둥 — 가장 높게
"""
from __future__ import annotations
import math
from .render import _dominant_cluster


# ── ACI(AutoCAD Color Index) → HTML hex ──────────────────────────
_ACI = {
    1: "ff0000", 2: "ffff00", 3: "00ff00",
    4: "00ffff", 5: "0070ff", 6: "ff00ff",
    7: "ffffff", 8: "808080", 9: "c0c0c0",
    10: "ff4040", 30: "ff8000", 40: "bf8000",
    50: "bfbf00", 60: "80bf00", 70: "00bf00",
    80: "00bf40", 90: "00bf80", 100: "00bfbf",
    110: "0080bf", 120: "0040bf", 130: "4000bf",
    140: "8000bf", 150: "bf00bf", 160: "bf0080",
    170: "bf0040", 180: "bf0000", 190: "ff6060",
    200: "ffa060", 210: "ffff60", 220: "a0ff60",
    230: "60ffa0", 240: "60ffff", 250: "808080",
}


def _aci_hex(idx: int) -> str | None:
    """ACI 인덱스 → hex 색상(예: '4da3ff'). 매핑 없으면 None."""
    if idx in _ACI:
        return _ACI[idx]
    # 16-255 구간: 대략적 ACI 팔레트 보간
    return None


def _build_layer_map(objects: list[dict]) -> dict[int, dict]:
    """LAYER 객체 → {handle_int: {name, hex_color}} 매핑.

    dwgread JSON의 color.index가 ACI 값이고, color.rgb는 "XXYYZZ" 형식이지만
    앞 2바이트가 flags이므로 index 기반 팔레트를 우선 사용한다.
    index=256(by layer) / 0(by block) / 7(white/black) → None 반환(타입 기본색 사용).
    """
    m: dict[int, dict] = {}
    for o in objects:
        if o.get("object") != "LAYER":
            continue
        h = o.get("handle")
        if not (isinstance(h, list) and len(h) >= 1):
            continue
        key = h[-1]
        col_info = o.get("color", {})
        idx = col_info.get("index", 7) if isinstance(col_info, dict) else 7
        # 기본/by-layer/white·black 인덱스는 None → JS가 타입 기본색 사용
        if idx in (0, 7, 256):
            hex_color = None
        else:
            hex_color = _aci_hex(idx)
        m[key] = {"name": o.get("name", ""), "color": hex_color}
    return m


def _resolve_layer(layer_ref, layer_map: dict) -> tuple[str, str | None]:
    """layer 참조(핸들 리스트 또는 문자열) → (name, hex_color or None).

    색상이 None이면 JS가 타입 기본색을 사용한다.
    """
    if isinstance(layer_ref, list) and len(layer_ref) >= 1:
        info = layer_map.get(layer_ref[-1])
        if info:
            return info["name"], info["color"]   # color는 hex str 또는 None
    if isinstance(layer_ref, str):
        return layer_ref, None
    return "", None


def _poly_area(pts) -> float:
    """Shoelace formula 다각형 넓이."""
    n = len(pts)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1]
        a -= pts[j][0] * pts[i][1]
    return abs(a) / 2.0


def _footprint_polys(objects, layer_map, max_count, min_pts, max_pts, min_area):
    """모델 공간 LWPOLYLINE 중 면적 있는 것 → (pts, layer_name, hex_color) 목록.

    열린 폴리라인도 포함(3~max_pts 점, 면적 > min_area).
    """
    polys = []
    for o in objects:
        if o.get("entmode") != 2 or o.get("entity") != "LWPOLYLINE":
            continue
        pts = [(p[0], p[1]) for p in o.get("points", []) if len(p) >= 2]
        n = len(pts)
        if n < min_pts or n > max_pts:
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if area < min_area:
            continue
        lname, lcol = _resolve_layer(o.get("layer"), layer_map)
        polys.append((pts, lname, lcol))
        if len(polys) >= max_count:
            break
    return polys


def extrude(drawing, max_count: int = 4000, min_pts: int = 3, max_pts: int = 16,
            target_size: float = 100.0, base_height: float = 4.0,
            min_area_ratio: float = 1e-8) -> dict:
    """닫힌/열린 윤곽을 분류·정규화해 3D 오브젝트 목록으로 반환.

    반환 형식::

        {
          "objects": [
            {"points": [[x,y],...], "type": "rack"|"equipment"|"zone",
             "layer": "레이어명", "color": "4da3ff", "area_norm": 0.002},
            ...
          ],
          "base_height": 4.0,
          "count": N,
          "span": 원본_최대변,
          "type_counts": {"rack": N, "equipment": M, "zone": K}
        }
    """
    layer_map = _build_layer_map(drawing.objects)

    # bbox 추정용으로 전체 폴리라인 좌표 수집
    all_pts = [p for o in drawing.objects
               if o.get("entmode") == 2 and o.get("entity") == "LWPOLYLINE"
               for raw in o.get("points", []) if len(raw) >= 2
               for p in [(raw[0], raw[1])]]
    if not all_pts:
        return {"objects": [], "base_height": base_height, "count": 0, "span": 0.0,
                "type_counts": {}}

    xs_all = [p[0] for p in all_pts]; ys_all = [p[1] for p in all_pts]
    span_full = max(max(xs_all) - min(xs_all), max(ys_all) - min(ys_all)) or 1.0
    min_area = span_full * span_full * min_area_ratio

    raw = _footprint_polys(drawing.objects, layer_map, max_count, min_pts, max_pts, min_area)
    if not raw:
        return {"objects": [], "base_height": base_height, "count": 0, "span": 0.0,
                "type_counts": {}}

    # dominant_cluster로 좌표 이상치 제거
    pts_list = [pts for pts, _, _ in raw]
    meta_map = {id(pts): (lname, lcol) for pts, lname, lcol in raw}
    filtered_pts = _dominant_cluster(pts_list)
    filtered = [(pts, *meta_map[id(pts)]) for pts in filtered_pts]

    xs = [p[0] for pts, _, _ in filtered for p in pts]
    ys = [p[1] for pts, _, _ in filtered for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    span = max(maxx - minx, maxy - miny) or 1.0
    s = target_size / span
    ref_area = span * span

    objects = []
    for pts, lname, lcol in filtered:
        norm_pts = [[round((x - cx) * s, 3), round((y - cy) * s, 3)]
                    for x, y in pts]
        area = _poly_area(pts)
        area_norm = min(area / ref_area, 1.0)

        # 면적 기반 분류 (span² 대비 비율)
        if area_norm > 0.05:
            obj_type = "zone"        # 큰 구역(시트 경계, 방)
        elif area_norm > 0.002:
            obj_type = "equipment"   # 중간 장비 (분전반 등)
        else:
            obj_type = "rack"        # 소형 (랙, 기둥, 심볼)

        objects.append({
            "points": norm_pts,
            "type": obj_type,
            "layer": lname,
            "color": lcol,
            "area_norm": round(area_norm, 6),
        })

    counts: dict[str, int] = {}
    for o in objects:
        counts[o["type"]] = counts.get(o["type"], 0) + 1

    return {
        "objects": objects,
        "base_height": round(base_height, 3),
        "count": len(objects),
        "span": round(span, 1),
        "type_counts": counts,
    }
