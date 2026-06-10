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

# robust bbox 계산 시 무시할 양끝 분위수
_CLIP_Q = 0.01
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


def json_to_svg(
    drawing, out_path: str | Path | None = None,
    max_count: int = 60000, width: int = 1400, stroke: float = 0.0,
    highlights: list | None = None,
) -> str:
    """dwgread JSON 도면을 SVG 문자열로 렌더(필요 시 파일 저장).

    highlights: [{"x":.., "y":.., "label":..}] 모델 좌표. 도면과 같은 변환으로
    위치에 마커(원+십자+라벨)를 그린다(예: 비표준 전압 위치).
    """
    polylines = _polylines(drawing.objects, max_count)
    polylines = _dominant_cluster(polylines)
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
        for hgl in highlights:
            hx, hy = hgl["x"], maxy - hgl["y"]
            lab = str(hgl.get("label", "")).replace("&", "&amp;").replace("<", "&lt;")
            lines.append(
                f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{r:.1f}" '
                f'fill="none" stroke="#f85149" stroke-width="{r*0.18:.2f}"/>'
                f'<line x1="{hx-r*1.6:.1f}" y1="{hy:.1f}" x2="{hx+r*1.6:.1f}" y2="{hy:.1f}" '
                f'stroke="#f85149" stroke-width="{r*0.12:.2f}"/>'
                f'<line x1="{hx:.1f}" y1="{hy-r*1.6:.1f}" x2="{hx:.1f}" y2="{hy+r*1.6:.1f}" '
                f'stroke="#f85149" stroke-width="{r*0.12:.2f}"/>'
                f'<text x="{hx+r*1.4:.1f}" y="{hy-r*1.4:.1f}" fill="#f85149" '
                f'stroke="none">{lab}</text>'
            )
        lines.append("</g>")

    lines.append("</svg>")
    svg = "\n".join(lines)

    if out_path:
        Path(out_path).write_text(svg, encoding="utf-8")
    return svg


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
