"""
Claude (Anthropic API) 번역기.

공식 Anthropic Python SDK(`anthropic`)를 사용한다.
masked XML(<x>…</x>로 보호된 수치·식별자)을 보존하며 중국어→한국어로 번역한다.

⚠️ 주의: 이 백엔드는 도면 텍스트를 외부(Anthropic API)로 전송한다.
   폐쇄망/사규상 외부 전송이 금지된 환경에서는 Ollama/vLLM 로컬 백엔드를 사용할 것.

환경변수:
    ANTHROPIC_API_KEY   필수 — API 키
    ANTHROPIC_MODEL     선택 — 모델 ID (기본: claude-sonnet-4-6)

사용 예:
    tr = ClaudeTranslator()                      # 기본 Sonnet 4.6
    tr = ClaudeTranslator(model="claude-haiku-4-5")
"""
from __future__ import annotations

import json
import os

_LANG_NAME = {
    "zh": "중국어",
    "ko": "한국어",
    "en": "영어",
    "ja": "일본어",
}

_DEFAULT_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = (
    "당신은 데이터센터 전기 도면 전문 번역가입니다. "
    "입력으로 받은 각 문자열을 {src}에서 {tgt}로 정확하게 번역하세요. "
    "전기/공조 기술 용어를 정확히 옮기고, 번역문만 출력하세요. "
    "규칙: (1) <x>…</x> 태그 안의 내용(수치·단위·식별자)은 번역하지 말고 "
    "태그까지 그대로 보존합니다. (2) 입력 개수와 출력 개수가 정확히 같아야 하며 "
    "순서를 유지합니다. (3) 설명·메모를 덧붙이지 마세요."
)

# 입력 배열 → 같은 길이의 번역 배열 (구조화 출력으로 길이·순서 보장)
_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["translations"],
    "additionalProperties": False,
}


class ClaudeTranslator:
    """Anthropic Claude 번역기 (Translator 프로토콜).

    Args:
        model:   모델 ID (기본: ANTHROPIC_MODEL 환경변수 → claude-sonnet-4-6)
        api_key: API 키 (기본: ANTHROPIC_API_KEY 환경변수)
    """

    def __init__(self, model: str | None = None, api_key: str | None = None):
        import anthropic  # 지연 임포트 (미설치 환경에서 다른 백엔드 영향 없음)
        self.model = model or os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
        self._client = anthropic.Anthropic(api_key=api_key)  # None이면 환경변수 사용

    # ── 한 묶음을 1회 호출로 번역 ─────────────────────────────────
    def _translate_chunk(self, texts: list[str], source: str, target: str) -> list[str]:
        src = _LANG_NAME.get(source, source)
        tgt = _LANG_NAME.get(target, target)
        system = _SYSTEM_PROMPT.format(src=src, tgt=tgt)
        user = (
            f"다음 {src} 기술 텍스트 {len(texts)}개를 {tgt}로 번역해 "
            "translations 배열로 반환하세요(입력과 동일한 순서·개수):\n"
            + json.dumps(texts, ensure_ascii=False)
        )
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude가 요청을 거부했습니다(refusal).")
        text = next(b.text for b in resp.content if b.type == "text")
        out = json.loads(text).get("translations", [])
        if len(out) != len(texts):
            raise RuntimeError(
                f"번역 개수 불일치: 입력 {len(texts)} ≠ 출력 {len(out)}")
        return out

    # ── 배치 번역 (Translator 프로토콜) ───────────────────────────
    def translate_batch(
        self, texts: list[str], target: str, source: str | None = None
    ) -> list[str]:
        """masked XML 문자열 목록을 번역해 같은 길이의 목록으로 반환."""
        src = source or "zh"
        # 빈 문자열은 호출에서 제외하고 자리만 유지
        idx = [i for i, t in enumerate(texts) if t and t.strip()]
        payload = [texts[i] for i in idx]
        if not payload:
            return list(texts)

        results = list(texts)
        try:
            out = self._translate_chunk(payload, src, target)
            for i, tr in zip(idx, out):
                results[i] = tr
        except Exception:
            # 배치 실패 시 항목별로 1회씩 재시도, 그래도 실패하면 원문 보존
            for i in idx:
                try:
                    results[i] = self._translate_chunk([texts[i]], src, target)[0]
                except Exception:
                    results[i] = texts[i]
        return results

    def __repr__(self) -> str:
        return f"ClaudeTranslator(model={self.model!r})"
