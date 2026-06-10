"""
이미지컷 렌더링.

두 경로:
  1) json_to_svg() — dwgread JSON 지오메트리를 직접 SVG로 렌더(권장, 전체 도면).
     LINE/LWPOLYLINE/ARC/CIRCLE를 폴리라인으로 변환하고 robust bbox로 뷰박스 결정.
  2) to_svg() — libredwg dwg2SVG 래퍼(복잡한 도면에서 부분 렌더 가능성).
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path
from shutil import which

# bbox 양끝 클립 분위수. dominant_cluster가 좌표계 이상치를 이미 제거하므로
# 0(=실제 min/max)으로 둔다. 퍼센타일 클립은 시트 가장자리를 잘라낸다.
_CLIP_Q = 0.0
_ARC_STEPS = 24


def _polylines(objects: list[dict], max_count: int,
               model_only: bool = True) -> list[list[tuple[float, float]]]:
    """엔티티를 (x,y) 폴리라인 목록으로 변환. model_only면 모델 공간(entmode 2)만."""
    out: list[list[tuple[float, float]]] = []
    for o in objects:
        if model_only and o.get("entmode") != 2:
            continue
        t = o.get("entity")
        if t == "LINE":
            s, e = o.get("start"), o.get("end")
            if s and e:
                out.append([(s[0], s[1]), (e[0], e[1])])
        elif t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in o.get("points", []) if len(p) >= 2]
            if len(pts) >= 2:
                if o.get("flag", 0) & 1 and pts[0] != pts[-1]:
                    pts.append(pts[0])  # 닫힘
                out.append(pts)
        elif t == "CIRCLE":
            c, r = o.get("center"), o.get("radius")
            if c and r:
                out.append([(c[0] + r * math.cos(a), c[1] + r * math.sin(a))
                            for a in [i / _ARC_STEPS * 2 * math.pi
                                      for i in range(_ARC_STEPS + 1)]])
        elif t == "ARC":
            c, r = o.get("center"), o.get("radius")
            a0, a1 = o.get("start_angle", 0.0), o.get("end_angle", 2 * math.pi)
            if c and r is not None:
                if a1 < a0:
                    a1 += 2 * math.pi
                n = _ARC_STEPS
                out.append([(c[0] + r * math.cos(a0 + (a1 - a0) * i / n),
                             c[1] + r * math.sin(a0 + (a1 - a0) * i / n))
                            for i in range(n + 1)])
        if len(out) >= max_count:
            break
    return out


def _median(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n else 0.0


def _dominant_cluster(polylines, k: float = 6.0):
    """중앙값±k·MAD 창에 드는 폴리라인만 남긴다(좌표계가 섞인 도면 대응)."""
    if len(polylines) < 50:   # 작은 도면은 클러스터 분리 불필요(퇴화 방지)
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


def json_to_svg(
    drawing, out_path: str | Path | None = None,
    max_count: int = 60000, width: int = 1400, stroke: float = 0.0,
    highlights: list | None = None, bounds: tuple | None = None,
    boxes: list | None = None,
) -> str:
    """dwgread JSON 도면을 SVG 문자열로 렌더(필요 시 파일 저장).

    highlights: [{"x":.., "y":.., "label":..}] 모델 좌표. 도면과 같은 변환으로
    위치에 마커(원+십자+라벨)를 그린다(예: 비표준 전압 위치).
    bounds: (minx,miny,maxx,maxy) 지정 시 해당 구획만 렌더.
    boxes: [{"bounds":[x0,y0,x1,y1], "label":..}] 구획 경계 사각형 오버레이.
    """
    polylines = _polylines(drawing.objects, max_count)
    polylines = _dominant_cluster(polylines)
    if bounds:
        polylines = _clip(polylines, bounds)
    if not polylines:
        raise RuntimeError("렌더할 도형이 없습니다.")
    if bounds:
        minx, miny, maxx, maxy = bounds
    else:
        minx, miny, maxx, maxy = _robust_bounds(polylines)
    w = (maxx - minx) or 1.0
    h = (maxy - miny) or 1.0
    height = int(width * h / w)
    sw = stroke or (w / width)  # 화면 1px 두께

    def fmt(pl):
        # Y 뒤집기(CAD: 위로 +, SVG: 아래로 +)
        return " ".join(f"{x:.2f},{(maxy - y):.2f}" for x, y in pl
                        if minx - w <= x <= maxx + w)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {w:.2f} {h:.2f}" style="background:#0f1419">',
        f'<g transform="translate({-minx:.2f},0)" stroke="#8fd3ff" '
        f'stroke-width="{sw:.4f}" fill="none" stroke-linecap="round">',
    ]
    drawn = 0
    for pl in polylines:
        pts = fmt(pl)
        if pts.count(",") >= 1 and " " in pts:
            lines.append(f'<polyline points="{pts}"/>')
            drawn += 1
    lines.append("</g>")

    # 하이라이트 마커
    if highlights:
        r = w * 0.012
        fs = w * 0.016
        lines.append(f'<g transform="translate({-minx:.2f},0)" '
                     f'font-family="sans-serif" font-size="{fs:.1f}">')
        def _esc(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        for hgl in highlights:
            hx, hy = hgl["x"], maxy - hgl["y"]
            col = hgl.get("color", "#f85149")  # 기본 빨강(위반)
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
            # 도면 위 라벨은 짧게(겹침 방지). 전체 제목은 표에서 확인.
            full = str(bx.get("title") or bx.get("label", ""))
            short = full if len(full) <= 16 else full[:15] + "…"
            short = short.replace("&", "&amp;").replace("<", "&lt;")
            lines.append(
                f'<rect x="{x0:.1f}" y="{ry:.1f}" width="{x1-x0:.1f}" height="{y1-y0:.1f}"/>'
                f'<text x="{x0+bw*4:.1f}" y="{ry-fs*0.4:.1f}" fill="#d29922" stroke="none" '
                f'font-size="{fs:.1f}" font-family="sans-serif">{short}</text>'
            )
        lines.append("</g>")

    lines.append("</svg>")
    svg = "\n".join(lines)

    if out_path:
        Path(out_path).write_text(svg, encoding="utf-8")
    return svg


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
            hx, hy = hgl["x"], hgl["y"]          # matplotlib은 Y 위로(+) → 뒤집지 않음
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
