"""
번역 결과를 도면에 재삽입 (제자리 교체 방식).

기본 읽기 경로(dwgread JSON)는 되돌려 저장이 어렵다(쓰기 불안정).
따라서 **DXF 입력**에 대해 ezdxf로 TEXT/MTEXT를 제자리 교체하고 DXF로 저장한다.
DWG 입력은 dwg2dxf로 먼저 변환을 시도한다(복잡한 도면은 BLOCK_HEADER 등으로 실패 가능).

MTEXT는 번역문으로 교체하면서 인라인 포맷 코드는 단순화된다(가독 우선).
원문 보존이 필요하면 별도 레이어 오버레이 방식(render.json_to_svg texts=)을 권장.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from shutil import which

from .text import clean_mtext
from .translate import glossary_translate, translate_texts


def _ensure_dxf(in_path: str | Path) -> tuple[Path, Path | None]:
    """입력을 ezdxf가 읽을 수 있는 DXF 경로로 보장.

    .dxf  → 그대로 사용 (tmp 없음)
    .dwg  → dwg2dxf로 임시 DXF 변환 (호출자가 tmp 정리)
    반환: (dxf_path, tmp_path|None)
    """
    p = Path(in_path)
    suffix = p.suffix.lower()
    if suffix == ".dxf":
        return p, None
    if suffix == ".dwg":
        if not which("dwg2dxf"):
            raise RuntimeError(
                "dwg2dxf(libredwg)가 없어 DWG를 DXF로 변환할 수 없습니다.\n"
                "설치: brew install libredwg (mac) / 소스 빌드(Linux)"
            )
        fd, tmp = tempfile.mkstemp(suffix=".dxf")
        os.close(fd)
        proc = subprocess.run(
            ["dwg2dxf", "-y", "-o", tmp, str(p)],
            capture_output=True, text=True,
        )
        tmp_path = Path(tmp)
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(
                "dwg2dxf 변환 실패 — 복잡한 도면은 DXF 변환이 지원되지 않을 수 있습니다.\n"
                + (proc.stderr or "")[-600:]
            )
        return tmp_path, tmp_path
    raise ValueError(f"지원하지 않는 형식: {suffix} (.dwg/.dxf 만 제자리 교체 가능)")


def translate_dxf(
    in_path: str | Path,
    out_path: str | Path,
    translator=None,
    glossary: dict[str, str] | None = None,
    target: str = "ko",
    source: str | None = "zh",
    cache=None,
) -> dict:
    """DXF/DWG의 TEXT/MTEXT를 번역해 제자리 교체 후 DXF로 저장. 통계 dict 반환.

    translator=None 이면 사전(glossary)만으로 즉시 치환한다(외부 엔진 불필요).
    그 외에는 translator(Argos/Ollama/DeepL/Mock)로 번역한다.
    """
    import ezdxf

    glossary = glossary or {}
    src_dxf, tmp_dxf = _ensure_dxf(in_path)
    try:
        doc = ezdxf.readfile(str(src_dxf))
        msp = doc.modelspace()

        ents, srcs = [], []
        for e in msp.query("TEXT MTEXT"):
            raw = e.dxf.text if e.dxftype() == "TEXT" else e.text
            clean = clean_mtext(raw)
            if clean:
                ents.append(e)
                srcs.append(clean)

        if translator is None:
            translations = [glossary_translate(s, glossary) for s in srcs]
        else:
            translations = translate_texts(
                srcs, translator, glossary=glossary,
                target=target, source=source, cache=cache,
            )

        replaced = 0
        for e, tr in zip(ents, translations):
            if not tr:
                continue
            if e.dxftype() == "TEXT":
                e.dxf.text = tr
            else:  # MTEXT
                e.text = tr
            replaced += 1

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(out_path))
        return {"entities": len(ents), "replaced": replaced, "out": str(out_path)}
    finally:
        if tmp_dxf is not None:
            tmp_dxf.unlink(missing_ok=True)
