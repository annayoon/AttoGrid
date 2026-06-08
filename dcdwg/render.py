"""
이미지컷 렌더링.

주의(검증 결과): libredwg `dwg2SVG`는 복잡한 실도면에서 일부 엔티티만 렌더했다.
전체 도면 이미지컷은 향후 보강 대상이다(JSON 지오메트리 직접 렌더 또는 외부 렌더러).
여기서는 libredwg가 변환 가능한 경우에 한해 SVG를 생성한다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which


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
