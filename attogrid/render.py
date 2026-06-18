"""
이미지컷 렌더링.

두 경로:
  1) json_to_svg() — dwgread JSON 지오메트리를 직접 SVG로 렌더(권장, 전체 도면).
     LINE/LWPOLYLINE/ARC/CIRCLE/ELLIPSE/SPLINE/SOLID을 폴리라인으로 변환하고
     robust bbox로 뷰박스 결정. 레이어별 색상 반영.
  2) to_svg() — libredwg dwg2SVG 래퍼(복잡한 도면에서 부분 렌더 가능성).
"""
from __future__ import annotations

import math
import subprocess
from collections import defaultdict
from pathlib import Path
from shutil import which

# bbox 양끝 클립 분위수
_CLIP_Q = 0.0
# 곡선 분절 수 (24 → 90: 곡선이 훨씬 매끄러워짐)
_ARC_STEPS = 90

# ── 색상 시스템 ───────────────────────────────────────────────────────────

# AutoCAD Color Index (ACI) → #rrggbb (어두운 배경 기준으로 밝게 조정)
_ACI: dict[int, str] = {
    1:  "#ff4444",  # red
    2:  "#ffff44",  # yellow
    3:  "#44dd44",  # green
    4:  "#44dddd",  # cyan
    5:  "#4488ff",  # blue
    6:  "#ff44ff",  # magenta
    7:  "#e8e8e8",  # white
    8:  "#888888",  # dark gray
    9:  "#bbbbbb",  # gray
    # 10단위 블록 대표색
    10: "#ff6666", 20: "#ffaa44", 30: "#ffdd44", 40: "#aaff44",
    50: "#44ffaa", 60: "#44ffff", 70: "#44aaff", 80: "#aa44ff",
    90: "#ff44aa", 100: "#ff4444", 110: "#ffaa00", 120: "#ffff00",
    130: "#00ff66", 140: "#00dddd", 150: "#0066ff", 160: "#6600ff",
    170: "#ff00ff",
    # 회색 계열
    250: "#555555", 251: "#777777", 252: "#999999",
    253: "#bbbbbb", 254: "#dddddd", 255: "#f0f0f0",
}
_DEFAULT_COLOR = "#8fd3ff"   # 미분류 기본(연한 파랑)


def _aci_rgb(idx: int) -> str:
    """ACI 인덱스 → #rrggbb. 표에 없는 인덱스는 10단위 블록으로 보간."""
    if idx in _ACI:
        return _ACI[idx]
    base = (idx // 10) * 10
    if base in _ACI:
        return _ACI[base]
    # HSV 계산: ACI 10–249는 24단계 색조 × 명도/채도 변형
    hue_block = ((idx - 10) // 10) % 24 if idx >= 10 else 0
    h = hue_block / 24.0
    s = 0.9
    v = 1.0
    i = int(h * 6)
    f = h * 6 - i
    p, q, t_v = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    rgb_map = [(v, t_v, p), (q, v, p), (p, v, t_v),
               (p, q, v), (t_v, p, v), (v, p, q)]
    r, g, b = rgb_map[i % 6]
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def _parse_rgb(s: str) -> str | None:
    """libredwg rgb 필드 '000000'/'c3rrggbb' → #rrggbb. 검정·빈값은 None."""
    if not s:
        return None
    s = str(s).lstrip("#")
    if len(s) == 8:
        s = s[2:]   # 상위 플래그 바이트 제거
    if len(s) == 6 and s.lower() not in ("000000",):
        return f"#{s.lower()}"
    return None


def _build_layer_colors(objects: list[dict]) -> tuple[dict, dict]:
    """LAYER 객체 스캔 → (handle_tuple→color, name→color) 두 딕셔너리."""
    hcol: dict[tuple, str] = {}
    ncol: dict[str, str] = {}
    for o in objects:
        if o.get("object") != "LAYER":
            continue
        name = o.get("name") or ""
        ci = o.get("color") or {}
        idx = ci.get("index", 7)
        rgb = str(ci.get("rgb") or "")
        # RGB 필드 우선, 없으면 ACI 인덱스 (0·256=BYLAYER 제외)
        col = _parse_rgb(rgb) or _aci_rgb(int(idx) if idx not in (0, 256) else 7)
        if name:
            ncol[name] = col
        h = o.get("handle")
        if h is not None:
            key = tuple(h) if isinstance(h, list) else (h,)
            hcol[key] = col
    return hcol, ncol


def _ent_color(o: dict, hcol: dict, ncol: dict) -> str:
    """엔티티의 유효 색상 결정 (BYLAYER이면 레이어 색 참조)."""
    ci = o.get("color") or {}
    idx = ci.get("index", 256)
    rgb = str(ci.get("rgb") or "")
    if idx not in (0, 256):
        return _parse_rgb(rgb) or _aci_rgb(int(idx))
    # BYLAYER: 레이어 핸들 또는 이름으로 조회
    layer = o.get("layer")
    if isinstance(layer, list):
        c = hcol.get(tuple(layer))
        if c:
            return c
    elif isinstance(layer, str):
        c = ncol.get(layer)
        if c:
            return c
    return _DEFAULT_COLOR


# ── 엔티티 파서 ──────────────────────────────────────────────────────────

def _arc_pts(c, r: float, a0: float, a1: float,
             steps: int | None = None) -> list[tuple[float, float]]:
    """호(ARC/CIRCLE) 점 목록. 각도: 라디안."""
    if a1 < a0:
        a1 += 2 * math.pi
    span = a1 - a0
    n = (max(2, int(span / (2 * math.pi) * _ARC_STEPS) + 1)
         if steps is None else steps)
    return [(c[0] + r * math.cos(a0 + span * i / n),
             c[1] + r * math.sin(a0 + span * i / n))
            for i in range(n + 1)]


def _parse_entities(
    objects: list[dict], max_count: int, model_only: bool = True,
    hcol: dict | None = None, ncol: dict | None = None,
) -> list[tuple[list[tuple[float, float]], str]]:
    """엔티티 → [(pts, color), ...] 목록."""
    hcol = hcol or {}
    ncol = ncol or {}
    out: list[tuple[list[tuple[float, float]], str]] = []

    for o in objects:
        if model_only and o.get("entmode") != 2:
            continue
        t = o.get("entity")
        pts: list[tuple[float, float]] | None = None

        if t == "LINE":
            s, e = o.get("start"), o.get("end")
            if s and e:
                pts = [(s[0], s[1]), (e[0], e[1])]

        elif t == "LWPOLYLINE":
            raw = [(p[0], p[1]) for p in o.get("points", []) if len(p) >= 2]
            if len(raw) >= 2:
                if o.get("flag", 0) & 1 and raw[0] != raw[-1]:
                    raw.append(raw[0])
                pts = raw

        elif t == "CIRCLE":
            c, r = o.get("center"), o.get("radius")
            if c and r:
                pts = _arc_pts(c, r, 0.0, 2 * math.pi, _ARC_STEPS)

        elif t == "ARC":
            c, r = o.get("center"), o.get("radius")
            a0 = float(o.get("start_angle") or 0.0)
            a1 = float(o.get("end_angle") or (2 * math.pi))
            if c and r is not None:
                pts = _arc_pts(c, r, a0, a1)

        elif t == "ELLIPSE":
            c = o.get("center")
            # 장축 벡터: 여러 필드명 시도
            mv = (o.get("sm_axis") or o.get("major_axis")
                  or o.get("axis") or o.get("extrusion"))
            ratio = float(o.get("axis_ratio") or o.get("b")
                          or o.get("ratio") or 1.0)
            a0 = float(o.get("start_param") or 0.0)
            a1 = float(o.get("end_param") or (2 * math.pi))
            if c and mv and len(mv) >= 2:
                mx, my = mv[0], mv[1]
                r_maj = math.hypot(mx, my)
                if r_maj == 0:
                    continue
                r_min = r_maj * min(max(ratio, 0.001), 1.0)
                rot = math.atan2(my, mx)
                if a1 < a0:
                    a1 += 2 * math.pi
                n = _ARC_STEPS
                raw = []
                for i in range(n + 1):
                    tp = a0 + (a1 - a0) * i / n
                    ex = r_maj * math.cos(tp)
                    ey = r_min * math.sin(tp)
                    raw.append((
                        c[0] + ex * math.cos(rot) - ey * math.sin(rot),
                        c[1] + ex * math.sin(rot) + ey * math.cos(rot),
                    ))
                pts = raw

        elif t == "SPLINE":
            # 피팅점 → 제어점 순으로 시도
            for key in ("fit_pts", "ctrl_pts", "points"):
                raw = o.get(key) or []
                if raw:
                    cand = [(p[0], p[1]) for p in raw if len(p) >= 2]
                    if len(cand) >= 2:
                        pts = cand
                        break

        elif t == "SOLID":
            corners: list[tuple[float, float]] = []
            for key in ("corner1", "corner2", "corner3", "corner4"):
                p = o.get(key)
                if p and len(p) >= 2:
                    corners.append((p[0], p[1]))
            if len(corners) >= 3:
                # SOLID는 지그재그 순서로 저장되므로 올바른 사각형 순서로 재배치
                if len(corners) == 4:
                    corners = [corners[0], corners[1],
                               corners[3], corners[2], corners[0]]
                else:
                    corners.append(corners[0])
                pts = corners

        if pts and len(pts) >= 2:
            col = _ent_color(o, hcol, ncol)
            out.append((pts, col))

        if len(out) >= max_count:
            break

    return out


def _polylines(objects: list[dict], max_count: int,
               model_only: bool = True) -> list[list[tuple[float, float]]]:
    """하위 호환용: (pts, color) → pts 만 반환."""
    return [pts for pts, _ in _parse_entities(objects, max_count, model_only)]


# ── 통계/클러스터 헬퍼 ────────────────────────────────────────────────────

def _median(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n else 0.0


def _dominant_cluster(polylines, k: float = 6.0):
    """중앙값±k·MAD 창에 드는 폴리라인만 남긴다(좌표계가 섞인 도면 대응)."""
    if len(polylines) < 50:
        return polylines
    cx = [sum(p[0] for p in pl) / len(pl) for pl in polylines]
    cy = [sum(p[1] for p in pl) / len(pl) for pl in polylines]
    mx, my = _median(cx), _median(cy)
    madx = _median([abs(x - mx) for x in cx]) or 1.0
    mady = _median([abs(y - my) for y in cy]) or 1.0
    keep = []
    for pl, x, y in zip(polylines, cx, cy):
        if abs(x - mx) <= k * madx and abs(y - my) <= k * mady:
            keep.append(pl)
    return keep or polylines


def _robust_bounds(polylines) -> tuple[float, float, float, float]:
    xs = sorted(p[0] for pl in polylines for p in pl)
    ys = sorted(p[1] for pl in polylines for p in pl)
    if not xs:
        return 0, 0, 1, 1
    lo = int(len(xs) * _CLIP_Q)
    hi = int(len(xs) * (1 - _CLIP_Q)) - 1
    lo, hi = max(0, lo), max(0, min(hi, len(xs) - 1))
    return xs[lo], ys[lo], xs[hi], ys[hi]


def _clip(polylines, bounds):
    """centroid가 bounds 안에 드는 폴리라인만 남긴다(구획 렌더용)."""
    bx0, by0, bx1, by1 = bounds
    out = []
    for pl in polylines:
        cx = sum(p[0] for p in pl) / len(pl)
        cy = sum(p[1] for p in pl) / len(pl)
        if bx0 <= cx <= bx1 and by0 <= cy <= by1:
            out.append(pl)
    return out


# ── SVG 렌더 ─────────────────────────────────────────────────────────────

def json_to_svg(
    drawing, out_path: str | Path | None = None,
    max_count: int = 60000, width: int = 3000, stroke: float = 0.0,
    highlights: list | None = None, bounds: tuple | None = None,
    boxes: list | None = None, texts: list | None = None,
) -> str:
    """dwgread JSON 도면을 SVG 문자열로 렌더(필요 시 파일 저장).

    highlights: [{"x":.., "y":.., "label":..}] 모델 좌표 마커.
    bounds: (minx,miny,maxx,maxy) 지정 시 해당 구획만 렌더.
    boxes: [{"bounds":[x0,y0,x1,y1], "label":..}] 구획 경계 오버레이.
    texts: [{"x":.., "y":.., "text":.., "height":..}] 번역 텍스트 오버레이.
    """
    hcol, ncol = _build_layer_colors(drawing.objects)
    entities = _parse_entities(drawing.objects, max_count, hcol=hcol, ncol=ncol)

    # dominant_cluster / clip 을 pts 목록에 적용하고, color 정보를 유지
    all_pts = [pts for pts, _ in entities]
    all_pts = _dominant_cluster(all_pts)
    survived = {id(pl) for pl in all_pts}
    entities = [(pts, col) for pts, col in entities if id(pts) in survived]

    if bounds:
        clipped_pts = _clip([pts for pts, _ in entities], bounds)
        survived2 = {id(pl) for pl in clipped_pts}
        entities = [(pts, col) for pts, col in entities if id(pts) in survived2]

    if not entities:
        raise RuntimeError("렌더할 도형이 없습니다.")

    if bounds:
        minx, miny, maxx, maxy = bounds
    else:
        minx, miny, maxx, maxy = _robust_bounds([pts for pts, _ in entities])

    w = (maxx - minx) or 1.0
    h = (maxy - miny) or 1.0
    height = int(width * h / w)

    def fmt(pl):
        return " ".join(f"{x:.2f},{(maxy - y):.2f}" for x, y in pl
                        if minx - w <= x <= maxx + w)

    def _esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {w:.2f} {h:.2f}" style="background:#0f1419">',
        '<style>polyline{vector-effect:non-scaling-stroke;stroke-width:1}</style>',
    ]

    # 레이어 색상별 그룹으로 묶어 렌더
    color_groups: dict[str, list] = defaultdict(list)
    for pts, col in entities:
        color_groups[col].append(pts)

    lines.append(f'<g transform="translate({-minx:.2f},0)" fill="none" stroke-linecap="round">')
    for col, pls in color_groups.items():
        lines.append(f'<g stroke="{col}">')
        drawn = 0
        for pl in pls:
            pts_str = fmt(pl)
            if pts_str.count(",") >= 1 and " " in pts_str:
                lines.append(f'<polyline points="{pts_str}"/>')
                drawn += 1
        lines.append("</g>")
    lines.append("</g>")

    # 하이라이트 마커
    if highlights:
        r = w * 0.012
        fs = w * 0.016
        lines.append(f'<g transform="translate({-minx:.2f},0)" '
                     f'font-family="sans-serif" font-size="{fs:.1f}">')
        for hgl in highlights:
            hx, hy = hgl["x"], maxy - hgl["y"]
            col = hgl.get("color", "#f85149")
            lab = _esc(hgl.get("label", ""))
            tip = _esc(hgl.get("tooltip", hgl.get("label", "")))
            lines.append(
                f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{r:.1f}" '
                f'fill="none" stroke="{col}" stroke-width="{r*0.18:.2f}">'
                f'<title>{tip}</title></circle>'
                f'<line x1="{hx-r*1.6:.1f}" y1="{hy:.1f}" x2="{hx+r*1.6:.1f}" y2="{hy:.1f}" '
                f'stroke="{col}" stroke-width="{r*0.12:.2f}"/>'
                f'<line x1="{hx:.1f}" y1="{hy-r*1.6:.1f}" x2="{hx:.1f}" y2="{hy+r*1.6:.1f}" '
                f'stroke="{col}" stroke-width="{r*0.12:.2f}"/>'
                f'<text x="{hx+r*1.4:.1f}" y="{hy-r*1.4:.1f}" fill="{col}" '
                f'stroke="none">{lab}</text>'
            )
        lines.append("</g>")

    # 구획 경계 사각형
    if boxes:
        bw = w * 0.0015
        fs = w * 0.011
        lines.append(f'<g transform="translate({-minx:.2f},0)" fill="none" '
                     f'stroke="#d29922" stroke-width="{bw:.2f}" '
                     f'stroke-dasharray="{w*0.01:.1f},{w*0.006:.1f}">')
        for bx in boxes:
            x0, y0, x1, y1 = bx["bounds"]
            ry = maxy - y1
            full = str(bx.get("title") or bx.get("label", ""))
            short = full if len(full) <= 16 else full[:15] + "…"
            short = short.replace("&", "&amp;").replace("<", "&lt;")
            lines.append(
                f'<rect x="{x0:.1f}" y="{ry:.1f}" width="{x1-x0:.1f}" height="{y1-y0:.1f}"/>'
                f'<text x="{x0+bw*4:.1f}" y="{ry-fs*0.4:.1f}" fill="#d29922" stroke="none" '
                f'font-size="{fs:.1f}" font-family="sans-serif">{short}</text>'
            )
        lines.append("</g>")

    # 번역 텍스트 오버레이 — 겹침 회피 배치
    #
    # 1) 실제 글자 높이 존중, 과대/과소만 캡
    # 2) 큰 글자 우선 그리디 배치: 겹치면 생략 (panzoom 확대 시 SVG 벡터 재렌더)
    if texts:
        default_h = w * 0.004
        min_h     = w * 0.0009
        max_h     = w * 0.02

        prepared = []
        for tx in texts:
            s = _esc(tx.get("text", ""))
            if not s:
                continue
            fh = tx.get("height") or default_h
            fh = max(min_h, min(float(fh), max_h))
            prepared.append((fh, float(tx["x"]), maxy - float(tx["y"]), s,
                             len(tx.get("text", ""))))
        prepared.sort(key=lambda row: -row[0])

        placed: list[tuple[float, float, float, float]] = []

        def _hit(b):
            for p in placed:
                if not (b[2] < p[0] or b[0] > p[2] or b[3] < p[1] or b[1] > p[3]):
                    return True
            return False

        lines.append(f'<g transform="translate({-minx:.2f},0)" '
                     f'fill="#ffd479" stroke="none" font-family="sans-serif">')
        for fh, x, y, s, n in prepared:
            box = (x, y - fh, x + n * fh * 0.62, y)
            if _hit(box):
                continue
            placed.append(box)
            lines.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fh:.1f}">{s}</text>')
        lines.append("</g>")

    lines.append("</svg>")
    svg = "\n".join(lines)

    if out_path:
        Path(out_path).write_text(svg, encoding="utf-8")
    return svg


# ── PNG 렌더 ─────────────────────────────────────────────────────────────

def json_to_png(
    drawing, out_path: str | Path,
    max_count: int = 80000, width_px: int = 2400, dpi: int = 150,
    highlights: list | None = None, bounds: tuple | None = None,
) -> str:
    """dwgread JSON 도면을 PNG로 렌더(matplotlib). highlights 마커·bounds 구획 지원."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    polylines = _polylines(drawing.objects, max_count)
    polylines = _dominant_cluster(polylines)
    if bounds:
        polylines = _clip(polylines, bounds)
    segs = [pl for pl in polylines if len(pl) >= 2]
    if not segs:
        raise RuntimeError("렌더할 도형이 없습니다.")
    minx, miny, maxx, maxy = bounds if bounds else _robust_bounds(polylines)
    w = (maxx - minx) or 1.0
    h = (maxy - miny) or 1.0

    win = width_px / dpi
    fig = plt.figure(figsize=(win, max(1.0, win * h / w)), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#0f1419")
    fig.set_facecolor("#0f1419")
    ax.add_collection(LineCollection(segs, linewidths=0.25, colors="#8fd3ff"))

    if highlights:
        for hgl in highlights:
            hx, hy = hgl["x"], hgl["y"]
            col = hgl.get("color", "#f85149")
            ax.plot(hx, hy, marker="o", mfc="none", mec=col, mew=1.2, ms=10)
            ax.annotate(str(hgl.get("label", "")), (hx, hy),
                        textcoords="offset points", xytext=(6, 6),
                        color=col, fontsize=8)

    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.axis("off")
    out_path = Path(out_path)
    fig.savefig(out_path, dpi=dpi, facecolor="#0f1419")
    plt.close(fig)
    return str(out_path)


def to_svg(dwg_path: str | Path, out_path: str | Path) -> Path:
    """dwg2SVG로 SVG 이미지컷 생성. (부분 렌더 가능성 있음)"""
    if not which("dwg2SVG"):
        raise RuntimeError("dwg2SVG(libredwg) 미설치. `brew install libredwg`")
    out_path = Path(out_path)
    svg = subprocess.run(
        ["dwg2SVG", str(dwg_path)], capture_output=True, text=True
    ).stdout
    if not svg.strip():
        raise RuntimeError("dwg2SVG가 빈 출력을 반환했습니다.")
    out_path.write_text(svg, encoding="utf-8")
    return out_path
