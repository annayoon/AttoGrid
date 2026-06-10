#!/usr/bin/env python3
"""
AttoGrid 데스크톱 앱 (pywebview).

Python 코어(attogrid)를 그대로 사용하고, UI는 ui/ 의 HTML/JS를 네이티브 창에 띄운다.
JS에서 `window.pywebview.api.<메서드>(...)`로 호출하면 Api 클래스 메서드가 실행된다.

Api 클래스는 창 없이도 단위 검증할 수 있도록 webview에 의존하지 않는다.
"""
from __future__ import annotations

import collections
from pathlib import Path

import attogrid

ROOT = Path(__file__).resolve().parent
GLOSSARY = ROOT / "attogrid" / "glossary" / "zh_ko.json"
RULES = ROOT / "attogrid" / "rules" / "datacenter.json"


class Api:
    """JS에서 호출되는 백엔드 API. 로드한 도면을 캐시해 재파싱을 피한다."""

    def __init__(self):
        self._cache: dict[str, attogrid.Drawing] = {}

    # --- 내부 ---
    def _load(self, path: str) -> attogrid.Drawing:
        if path not in self._cache:
            self._cache[path] = attogrid.read(path)
        return self._cache[path]

    # --- 파일 선택 (창이 있을 때만 동작) ---
    def open_dialog(self) -> str | None:
        import webview
        win = webview.windows[0]
        result = win.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("DWG/JSON (*.dwg;*.json)", "All files (*.*)"),
        )
        return result[0] if result else None

    # --- 요약 ---
    def inspect(self, path: str) -> dict:
        d = self._load(path)
        kinds = collections.Counter(
            o.get("entity") or o.get("object") or "?" for o in d.objects
        )
        return {
            "path": path,
            "objects": len(d.objects),
            "layers": len(d.layers),
            "entities": kinds.most_common(15),
        }

    # --- 텍스트/번역대상 ---
    def texts(self, path: str, translatable_only: bool = False, limit: int = 300) -> dict:
        d = self._load(path)
        items = attogrid.extract_texts(d)
        dist = collections.Counter(i.lang for i in items)
        rows = [
            {"lang": i.lang, "translatable": i.translatable, "text": i.text}
            for i in items
            if not translatable_only or i.translatable
        ][:limit]
        return {"total": len(items), "dist": dict(dist), "rows": rows}

    # --- 도면 미리보기 (JSON 지오메트리 직접 렌더) ---
    def render(self, path: str, max_count: int = 50000) -> dict:
        d = self._load(path)
        svg = attogrid.render.json_to_svg(d, max_count=max_count, width=1400)
        return {"svg": svg, "polylines": svg.count("<polyline")}

    # --- 2D→3D 압출 ---
    def model3d(self, path: str) -> dict:
        d = self._load(path)
        return attogrid.extrude(d)

    # --- 검증 ---
    def validate(self, path: str) -> dict:
        d = self._load(path)
        texts = [i.text for i in attogrid.extract_texts(d)]
        rules = attogrid.load_rules(RULES)
        findings = attogrid.validate(texts, rules)
        return {
            "ruleset": rules.get("name"),
            "count": len(findings),
            "findings": [
                {"severity": f.severity, "rule": f.rule,
                 "message": f.message, "context": f.context}
                for f in findings
            ],
        }

    # --- 번역 ---
    def translate(self, path: str, backend: str = "argos", limit: int = 50) -> dict:
        d = self._load(path)
        items = [i for i in attogrid.extract_texts(d) if i.translatable]
        if limit:
            items = items[:limit]
        glossary = attogrid.load_glossary(GLOSSARY)

        if backend == "mock":
            tr = attogrid.MockTranslator()
        elif backend == "deepl":
            tr = attogrid.DeepLTranslator()
        else:
            tr = attogrid.ArgosTranslator()

        srcs = [i.text for i in items]
        outs = attogrid.translate_texts(srcs, tr, glossary=glossary, target="ko", source="zh")
        return {
            "backend": backend,
            "count": len(srcs),
            "rows": [{"source": s, "translation": t} for s, t in zip(srcs, outs)],
        }


def main():
    import webview
    api = Api()
    webview.create_window(
        "AttoGrid — 데이터센터 DWG 도구  (by ATTO Research)",
        str(ROOT / "ui" / "index.html"),
        js_api=api,
        width=1100,
        height=760,
        min_size=(900, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
