"""
Ollama 로컬 LLM 번역기.

GPU 없는 서버에서도 CPU 추론으로 동작한다.
qwen2.5:14b 모델이 중국어→한국어 기술 번역에 최적.

사용 예:
    ollama pull qwen2.5:14b   # 서버에서 1회만 실행
    translator = OllamaTranslator()
    translator.translate_batch(["额定电压 380V"], target="ko", source="zh")
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


_LANG_NAME = {
    "zh": "중국어",
    "ko": "한국어",
    "en": "영어",
    "ja": "일본어",
}

_SYSTEM_PROMPT = (
    "당신은 데이터센터 전기 도면 전문 번역가입니다. "
    "중국어 기술 용어를 한국어로 정확하게 번역하세요. "
    "번역 결과만 출력하고 설명이나 메모는 절대 추가하지 마세요. "
    "<x> 태그 안의 내용은 번역하지 말고 그대로 보존하세요."
)


class OllamaTranslator:
    """Ollama REST API 번역기 — translate.Translator 프로토콜 구현.

    Args:
        model:   Ollama 모델명 (기본: qwen2.5:14b)
        host:    Ollama 서버 주소 (기본: http://localhost:11434)
        timeout: 요청 타임아웃 초 (기본: 60)
    """

    def __init__(
        self,
        model: str = "qwen2.5:14b",
        host: str = "http://localhost:11434",
        timeout: int = 60,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    # ── 단일 텍스트 번역 ───────────────────────────────────────────
    def _translate_one(self, text: str, source: str, target: str) -> str:
        src = _LANG_NAME.get(source, source)
        tgt = _LANG_NAME.get(target, target)
        prompt = f"다음 {src} 기술 텍스트를 {tgt}로 번역하세요:\n{text}"

        body = json.dumps({
            "model": self.model,
            "system": _SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 256,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                resp = json.loads(r.read())
            return resp.get("response", "").strip()
        except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(
                f"Ollama 번역 오류 ({self.host}): {e}\n"
                f"→ 서버 확인: ollama serve  /  모델 확인: ollama pull {self.model}"
            ) from e

    # ── 배치 번역 (Translator 프로토콜) ───────────────────────────
    def translate_batch(
        self, texts: list[str], target: str, source: str | None = None
    ) -> list[str]:
        """masked XML 문자열 목록을 번역해 같은 길이의 목록으로 반환."""
        src = source or "zh"
        results = []
        for text in texts:
            if not text or not text.strip():
                results.append(text)
                continue
            try:
                results.append(self._translate_one(text, src, target))
            except Exception as e:
                # 번역 실패 시 원문 반환 (전체 중단 방지)
                results.append(text)
        return results

    def __repr__(self) -> str:
        return f"OllamaTranslator(model={self.model!r}, host={self.host!r})"
