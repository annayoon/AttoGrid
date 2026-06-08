"""
텍스트 추출 + MTEXT 포맷 코드 정제 + 번역 대상 분류.

실파일에서 전압값(220V 등)이 MTEXT 폰트 코드 안에 묻혀 있었다:
  {\\Fxd-hzs,xd-hztxt|c0;220V\\F...;电源线就近接双电源箱}
clean_mtext()가 이런 제어코드를 제거한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 식별자/회로명 패턴 (번역 제외): CIRCUIT-A-12, R-01, ATS 등
_IDENTIFIER = re.compile(r"^[A-Z0-9][A-Z0-9\-_/\.]*$")

_RE_FONT = re.compile(r"\\[fF][^;]*;")
_RE_CTRL = re.compile(r"\\[CcHWQTApXKkLlOo][^\\;{}]*;?")
_RE_LEFTOVER = re.compile(r"\\[A-Za-z]")


def clean_mtext(s: str | None) -> str:
    """MTEXT 인라인 포맷 코드를 제거하고 순수 텍스트만 남긴다."""
    if not s:
        return ""
    s = _RE_FONT.sub("", s)
    s = _RE_CTRL.sub("", s)
    s = s.replace("\\P", " ")
    s = s.replace("{", "").replace("}", "")
    s = _RE_LEFTOVER.sub("", s)
    return s.strip()


def classify_language(s: str) -> str:
    if re.search(r"[가-힣]", s):
        return "ko"
    if re.search(r"[一-鿿]", s):
        return "zh"
    if re.search(r"[A-Za-z]", s):
        return "en"
    return "sym"


@dataclass
class TextItem:
    raw: str
    text: str          # 정제된 텍스트
    lang: str
    translatable: bool
    handle: str | None = None


def extract_texts(drawing) -> list[TextItem]:
    """TEXT/MTEXT 엔티티에서 정제된 텍스트 목록을 추출한다."""
    items: list[TextItem] = []
    for o in drawing.objects:
        t = o.get("entity")
        if t == "TEXT":
            raw = o.get("text_value")
        elif t == "MTEXT":
            raw = o.get("text")
        else:
            continue
        if not isinstance(raw, str):
            continue
        clean = clean_mtext(raw)
        if not clean:
            continue
        lang = classify_language(clean)
        # 식별자(영문/숫자 코드)는 번역 제외, 한·중·일 문장은 대상
        translatable = lang in ("ko", "zh") or not _IDENTIFIER.match(clean)
        if lang == "en" and _IDENTIFIER.match(clean):
            translatable = False
        items.append(TextItem(
            raw=raw, text=clean, lang=lang, translatable=translatable,
            handle=o.get("handle", {}).get("value") if isinstance(o.get("handle"), dict) else o.get("handle"),
        ))
    return items
