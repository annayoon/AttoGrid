"""
번역 (DeepL 기본, 교체 가능 구조).

핵심은 **번역 전후 보호 처리**다. 도면 텍스트에는 번역하면 안 되는 토큰이 섞여 있다:
  - 식별자/회로명:  CIRCUIT-A-12, HL3-2A-4.0A, ATS-1
  - 전기 수치/단위:  380V, 3200A, 1300KVA, 22.0KW, 2.5MPa
  - 규격 코드:       GB50370-2005

이런 토큰을 XML ignore 태그(<x>...</x>)로 감싸 백엔드가 건드리지 않게 하고,
도메인 용어(glossary)는 미리 한국어로 치환해 동일 태그로 보호함으로써
"용어 일관성 + 수치 보존"을 동시에 보장한다.

백엔드는 Translator 프로토콜만 만족하면 교체 가능:
  - DeepLTranslator : DEEPL_API_KEY 환경변수 사용 (운영)
  - MockTranslator  : 키 없이 보호/사전 로직 검증 (테스트/오프라인)
"""
from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# --- 보호 대상 패턴 (번역 금지) ---
_PROTECT = re.compile(
    r"""(
        \b[A-Z]{1,15}\d*(?:[-/][A-Z0-9.]+)+\b       # CIRCUIT-A-12, HL3-2A-4.0A, 3200A/4P
      | \bGB\s?\d+(?:[-－]\d+)?\b                    # GB50370-2005
      | \d+\.?\d*\s?(?:kV|KV|VAC|VDC|V|kVA|KVA|kW|KW|W|MPa|A|Hz)\b  # 전기 수치+단위
    )""",
    re.X,
)

_UNMASK = re.compile(r"<x>(.*?)</x>", re.S)


class Translator(Protocol):
    def translate_batch(
        self, texts: list[str], target: str, source: str | None = None
    ) -> list[str]:
        """masked XML 문자열 목록을 번역해 같은 길이의 목록으로 반환."""
        ...


# ----------------------- 보호/복원 -----------------------

def _spans(text: str, glossary: dict[str, str]) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    if glossary:
        keys = sorted(glossary, key=len, reverse=True)
        gre = re.compile("|".join(re.escape(k) for k in keys))
        for m in gre.finditer(text):
            spans.append((m.start(), m.end(), glossary[m.group(0)]))  # 한국어로 치환
    for m in _PROTECT.finditer(text):
        spans.append((m.start(), m.end(), m.group(0)))                # 원문 보존
    # 겹침 해소: 시작 빠른 것 우선, 같으면 긴 것 우선
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    chosen, last = [], -1
    for s, e, r in spans:
        if s >= last:
            chosen.append((s, e, r))
            last = e
    return chosen


def mask(text: str, glossary: dict[str, str]) -> str:
    """보호 토큰/사전 용어를 <x>…</x>로 감싼 XML 문자열 생성."""
    out, i = [], 0
    for s, e, r in _spans(text, glossary):
        out.append(html.escape(text[i:s]))
        out.append(f"<x>{html.escape(r)}</x>")
        i = e
    out.append(html.escape(text[i:]))
    return "".join(out)


def unmask(text: str) -> str:
    """<x> 태그 제거 + XML 이스케이프 복원."""
    parts, i = [], 0
    for m in _UNMASK.finditer(text):
        parts.append(html.unescape(text[i:m.start()]))
        parts.append(html.unescape(m.group(1)))
        i = m.end()
    parts.append(html.unescape(text[i:]))
    return "".join(parts)


# ----------------------- 백엔드 -----------------------

class MockTranslator:
    """키 없이 동작. 텍스트 노드는 그대로 두고(=식별 변환), 보호/사전 로직만 검증."""

    def translate_batch(self, texts, target, source=None):
        return list(texts)


class DeepLTranslator:
    """DeepL API 백엔드. DEEPL_API_KEY 환경변수 필요."""

    # DeepL 언어코드 매핑
    _LANG = {"ko": "KO", "zh": "ZH", "en": "EN", "ja": "JA"}

    def __init__(self, api_key: str | None = None):
        import deepl  # 지연 임포트
        key = api_key or os.environ.get("DEEPL_API_KEY")
        if not key:
            raise RuntimeError(
                "DEEPL_API_KEY가 없습니다. `export DEEPL_API_KEY=...` 후 다시 실행하세요."
            )
        self.client = deepl.Translator(key)

    def translate_batch(self, texts, target, source=None):
        if not texts:
            return []
        res = self.client.translate_text(
            texts,
            target_lang=self._LANG.get(target, target.upper()),
            source_lang=self._LANG.get(source) if source else None,
            tag_handling="xml",
            ignore_tags=["x"],
        )
        return [r.text for r in res]


# ----------------------- 고수준 API -----------------------

@dataclass
class TranslationCache:
    path: Path | None = None
    _data: dict = field(default_factory=dict)

    def load(self):
        if self.path and self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        return self

    def save(self):
        if self.path:
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=0),
                encoding="utf-8",
            )

    def key(self, src, target):
        return f"{target}{src}"


def load_glossary(path: str | Path) -> dict[str, str]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def translate_texts(
    texts: list[str],
    translator: Translator,
    glossary: dict[str, str] | None = None,
    target: str = "ko",
    source: str | None = "zh",
    batch_size: int = 45,
    cache: TranslationCache | None = None,
) -> list[str]:
    """원문 목록 -> 번역 목록. 중복은 1회만 번역(비용 절감), 캐시 지원."""
    glossary = glossary or {}
    # 고유 원문만 번역
    uniq = list(dict.fromkeys(texts))
    todo, result = [], {}
    for s in uniq:
        if cache and cache.key(s, target) in cache._data:
            result[s] = cache._data[cache.key(s, target)]
        else:
            todo.append(s)

    for i in range(0, len(todo), batch_size):
        chunk = todo[i:i + batch_size]
        masked = [mask(s, glossary) for s in chunk]
        out = translator.translate_batch(masked, target=target, source=source)
        for src, tr in zip(chunk, out):
            val = unmask(tr)
            result[src] = val
            if cache:
                cache._data[cache.key(src, target)] = val

    if cache:
        cache.save()
    return [result[s] for s in texts]
