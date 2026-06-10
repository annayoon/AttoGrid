"""
번역 결과를 도면에 재삽입.

기본 읽기 경로(dwgread JSON)는 되돌려 저장이 어렵다(쓰기 불안정).
따라서 **DXF 입력**에 대해 ezdxf로 TEXT/MTEXT를 제자리 교체하고 DXF로 저장한다.
DWG 입력은 먼저 dwg2dxf로 변환이 성공해야 한다(복잡한 도면은 실패할 수 있음).

MTEXT는 번역문으로 교체하면서 인라인 포맷 코드는 단순화된다(가독 우선).
원문 보존이 필요하면 별도 레이어 오버레이 방식을 권장.
"""
from __future__ import annotations

from pathlib import Path

from .text import clean_mtext
from .translate import translate_texts


def translate_dxf(
    in_path: str | Path,
    out_path: str | Path,
    translator,
    glossary: dict[str, str] | None = None,
    target: str = "ko",
    source: str | None = "zh",
    cache=None,
) -> dict:
    """DXF의 TEXT/MTEXT를 번역해 제자리 교체 후 저장. 통계 dict 반환."""
    import ezdxf

    doc = ezdxf.readfile(str(in_path))
    msp = doc.modelspace()

    ents, srcs = [], []
    for e in msp.query("TEXT MTEXT"):
        raw = e.dxf.text if e.dxftype() == "TEXT" else e.text
        clean = clean_mtext(raw)
        if clean:
            ents.append(e)
            srcs.append(clean)

    translations = translate_texts(
        srcs, translator, glossary=glossary, target=target, source=source, cache=cache
    )

    replaced = 0
    for e, tr in zip(ents, translations):
        if e.dxftype() == "TEXT":
            e.dxf.text = tr
        else:  # MTEXT
            e.text = tr
        replaced += 1

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_path))
    return {"entities": len(ents), "replaced": replaced, "out": str(out_path)}
