"""
OpenAI 호환 LLM 번역기.

Ollama / vLLM / LM Studio 등 /v1/chat/completions 엔드포인트를 지원하는
모든 서버에서 동작한다.

사용 예:
    # vLLM 서버
    tr = OllamaTranslator(host="http://10.0.98.99:8000")

    # 로컬 Ollama
    tr = OllamaTranslator(host="http://localhost:11434", model="qwen2.5:14b")
"""
from __future__ import annotations

import json
import os
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


def _fetch_first_model(host: str, timeout: int = 5) -> str | None:
    """서버의 첫 번째 모델 ID를 반환. 실패 시 None."""
    try:
        req = urllib.request.Request(f"{host}/v1/models")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        models = data.get("data", [])
        if models:
            return models[0]["id"]
    except Exception:
        pass
    return None


class OllamaTranslator:
    """OpenAI 호환 API 번역기 (vLLM / Ollama / LM Studio).

    모델을 지정하지 않으면 서버에서 사용 가능한 첫 번째 모델을 자동 선택.

    Args:
        model:   모델 ID (None이면 서버에서 자동 조회)
        host:    서버 주소 (기본: OLLAMA_HOST 환경변수 → http://10.0.98.99:8000)
        timeout: 요청 타임아웃 초 (기본: 60)
    """

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout: int = 60,
    ):
        self.host    = (host or os.environ.get("OLLAMA_HOST", "http://10.0.98.99:8000")).rstrip("/")
        self.timeout = timeout
        # 모델 자동 조회 (한 번만)
        self._model = model
        if self._model is None:
            self._model = _fetch_first_model(self.host, timeout=5) or "qwen2.5:14b"

    @property
    def model(self) -> str:
        return self._model

    # ── 단일 텍스트 번역 ───────────────────────────────────────────
    def _translate_one(self, text: str, source: str, target: str) -> str:
        src = _LANG_NAME.get(source, source)
        tgt = _LANG_NAME.get(target, target)
        user_msg = f"다음 {src} 기술 텍스트를 {tgt}로 번역하세요:\n{text}"

        import re as _re
        body = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            "temperature": 0.1,
            "max_tokens":  512,
            # Qwen3 thinking 모드 비활성화 (vLLM)
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.host}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                resp = json.loads(r.read())
            content = resp["choices"][0]["message"]["content"].strip()
            # Qwen3 thinking 태그 제거 (<think>...</think>)
            content = _re.sub(r"<think>.*?</think>", "", content, flags=_re.S).strip()
            return content
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
            raise RuntimeError(
                f"LLM 번역 오류 ({self.host}): {e}\n"
                f"→ 서버 확인: curl {self.host}/v1/models"
            ) from e

    # ── 배치 번역 (Translator 프로토콜) ───────────────────────────
    def translate_batch(
        self, texts: list[str], target: str, source: str | None = None
    ) -> list[str]:
        """masked XML 문자열 목록을 번역해 같은 길이의 목록으로 반환."""
        src     = source or "zh"
        results = []
        for text in texts:
            if not text or not text.strip():
                results.append(text)
                continue
            try:
                results.append(self._translate_one(text, src, target))
            except Exception:
                results.append(text)   # 실패 시 원문 보존
        return results

    def __repr__(self) -> str:
        return f"OllamaTranslator(model={self._model!r}, host={self.host!r})"
