"""
DWG/DXF 읽기.

검증 결과(실파일 4.8MB)에 따라 기본 경로는 `dwgread -O JSON`이다.
복잡한 실도면에서 dwg2dxf(DXF 변환)는 BLOCK_HEADER 에러로 잘리는 반면,
dwgread의 JSON 덤프는 전체 엔티티를 보존했다.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Drawing:
    """파싱된 도면. libredwg JSON 덤프를 감싼다."""
    source: Path
    data: dict
    objects: list = field(default_factory=list)

    @property
    def layers(self) -> list[dict]:
        return self.data.get("TABLES", {}).get("LAYER", [])

    def query(self, entity_type: str) -> list[dict]:
        return [o for o in self.objects if o.get("entity") == entity_type]


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


def read(path: str | Path) -> Drawing:
    """DWG 또는 DXF 파일을 읽어 Drawing으로 반환.

    .dwg  -> dwgread -O JSON (권장 경로)
    .json -> 기존 덤프 직접 로드 (캐시 재사용)
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    elif suffix == ".dwg":
        data = _dwg_to_json(path)
    else:
        raise ValueError(f"지원하지 않는 형식: {suffix} (현재 .dwg/.json 지원)")

    return Drawing(source=path, data=data, objects=data.get("OBJECTS", []))


def _dwg_to_json(path: Path) -> dict:
    if not _which("dwgread"):
        raise RuntimeError(
            "dwgread(libredwg)가 설치되어 있지 않습니다. `brew install libredwg`"
        )
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        proc = subprocess.run(
            ["dwgread", "-O", "JSON", "-o", str(out), str(path)],
            capture_output=True, text=True,
        )
        # libredwg은 비치명적 경고도 stderr에 출력하므로 산출물 존재로 성공 판정
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"dwgread 실패:\n{proc.stderr[-2000:]}")
        return json.loads(out.read_text(encoding="utf-8", errors="replace"))
    finally:
        out.unlink(missing_ok=True)
