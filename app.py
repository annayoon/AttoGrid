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

    def __init__(self, default_path: str | None = None):
        self._cache: dict[str, attogrid.Drawing] = {}
        self._default_path = default_path

    # 명령행으로 받은 파일 경로(있으면 UI가 자동 로드)
    def default_path(self) -> str | None:
        return self._default_path

    # --- 내부 ---
    def _load(self, path: str) -> attogrid.Drawing:
        if path not in self._cache:
            self._cache[path] = attogrid.read(path)
        return self._cache[path]

    # --- 파일 선택 (창이 있을 때만 동작) ---
    def open_dialog(self) -> str | None:
        import webview
        win = webview.windows[0]
        # macOS NSOpenPanel은 file_types 파싱이 까다로워 파일이 비활성화될 수 있으므로
        # 필터 없이 모든 파일을 선택 가능하게 연다.
        try:
            result = win.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False)
        except Exception:
            result = win.create_file_dialog(10)  # OPEN_DIALOG 폴백
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

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
    def render(self, path: str, max_count: int = 50000, highlights=None, boxes=None) -> dict:
        d = self._load(path)
        svg = attogrid.render.json_to_svg(
            d, max_count=max_count, width=1400, highlights=highlights, boxes=boxes)
        return {"svg": svg, "polylines": svg.count("<polyline")}

    # --- 도면 이미지 내보내기 (PNG/SVG) ---
    def export_image(self, path: str, fmt: str = "png",
                     with_markers: bool = False, out_path: str | None = None) -> dict:
        d = self._load(path)
        highlights = None
        if with_markers:
            highlights = self.locate_voltages(path, include_ok=True)["items"]
        if not out_path:
            out_path = self._save_dialog(fmt) or str(ROOT / f"drawing.{fmt}")
        p = Path(out_path).expanduser()
        if p.suffix.lower() not in (".png", ".svg"):
            p = p.with_suffix("." + fmt)

        if p.suffix.lower() == ".svg":
            attogrid.render.json_to_svg(d, out_path=str(p), highlights=highlights)
        else:
            attogrid.render.json_to_png(d, str(p), highlights=highlights)
        return {"path": str(p)}

    # --- 도면 구획 분할 (+ 구획별 제목·검증·번역대상 집계) ---
    def partition(self, path: str, method: str = "auto",
                  rows: int = 2, cols: int = 2) -> dict:
        from attogrid.partition import section_title
        d = self._load(path)
        secs = attogrid.partition(d, method=method, rows=rows, cols=cols)
        items = attogrid.extract_texts(d)
        rules = attogrid.load_rules(RULES)
        for s in secs:
            b = s["bounds"]
            inside = [it for it in items if it.x is not None
                      and b[0] <= it.x <= b[2] and b[1] <= it.y <= b[3]]
            findings = attogrid.validate([it.text for it in inside], rules)
            s["title"] = section_title(d, b) or s["label"]
            s["texts"] = len(inside)
            s["translatable"] = sum(1 for it in inside if it.translatable)
            s["violations"] = sum(1 for f in findings if f.severity != "info")
        return {"method": method, "count": len(secs), "sections": secs}

    # --- 구획별 이미지 저장 ---
    def export_sections(self, path: str, method: str = "auto", fmt: str = "png",
                        with_markers: bool = False, rows: int = 2, cols: int = 2,
                        out_dir: str | None = None) -> dict:
        from attogrid.partition import section_title
        d = self._load(path)
        secs = attogrid.partition(d, method=method, rows=rows, cols=cols)
        if not secs:
            return {"count": 0, "dir": None, "files": []}
        markers = self.locate_voltages(path, include_ok=True)["items"] if with_markers else None
        if not out_dir:
            out_dir = self._folder_dialog() or str(ROOT / "sections")
        outd = Path(out_dir).expanduser()
        outd.mkdir(parents=True, exist_ok=True)

        files = []
        for i, s in enumerate(secs, 1):
            b = tuple(s["bounds"])
            hl = ([h for h in markers if b[0] <= h["x"] <= b[2] and b[1] <= h["y"] <= b[3]]
                  if markers else None)
            title = section_title(d, b) or s["label"]
            safe = "".join(c for c in title if c.isalnum())[:20] or s["label"].replace(" ", "")
            name = f"{i:02d}_{safe}.{fmt}"
            fp = outd / name
            try:
                if fmt == "svg":
                    attogrid.render.json_to_svg(d, out_path=str(fp), bounds=b, highlights=hl)
                else:
                    attogrid.render.json_to_png(d, str(fp), bounds=b, highlights=hl)
                files.append(str(fp))
            except Exception:
                continue
        return {"count": len(files), "dir": str(outd), "files": files}

    # --- 구획(시트)별 번역 CSV ---
    def export_section_translations(self, path: str, method: str = "auto",
                                    backend: str = "argos", rows: int = 2, cols: int = 2,
                                    limit: int = 0, out_dir: str | None = None) -> dict:
        import csv
        import io
        from attogrid.partition import section_title

        d = self._load(path)
        secs = attogrid.partition(d, method=method, rows=rows, cols=cols)
        if not secs:
            return {"count": 0, "dir": None, "files": []}
        items = [it for it in attogrid.extract_texts(d) if it.translatable and it.x is not None]
        glossary = attogrid.load_glossary(GLOSSARY)
        tr = (attogrid.MockTranslator() if backend == "mock"
              else attogrid.DeepLTranslator() if backend == "deepl"
              else attogrid.ArgosTranslator())
        cache = attogrid.TranslationCache(Path(ROOT / ".attogrid_cache.json")).load()

        if not out_dir:
            out_dir = self._folder_dialog() or str(ROOT / "translations")
        outd = Path(out_dir).expanduser()
        outd.mkdir(parents=True, exist_ok=True)

        files = []
        for i, s in enumerate(secs, 1):
            b = s["bounds"]
            inside = [it for it in items
                      if b[0] <= it.x <= b[2] and b[1] <= it.y <= b[3]]
            if limit:
                inside = inside[:limit]
            if not inside:
                continue
            srcs = [it.text for it in inside]
            outs = attogrid.translate_texts(srcs, tr, glossary=glossary,
                                            target="ko", source="zh", cache=cache)
            title = section_title(d, b) or s["label"]
            safe = "".join(c for c in title if c.isalnum())[:20] or s["label"].replace(" ", "")
            fp = outd / f"{i:02d}_{safe}.csv"
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["원문", "번역", "X", "Y"])
            for it, t in zip(inside, outs):
                w.writerow([it.text, t, it.x, it.y])
            fp.write_text("﻿" + buf.getvalue(), encoding="utf-8")
            files.append(str(fp))
        return {"count": len(files), "dir": str(outd), "files": files, "backend": backend}

    def _folder_dialog(self) -> str | None:
        try:
            import webview
            win = webview.windows[0]
            r = win.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception:
            return None
        if not r:
            return None
        return r if isinstance(r, str) else r[0]

    # --- 전압의 도면상 위치 찾기 ---
    # include_ok=False: 위반(비표준)만 빨강. True: 정상 전압도 초록으로 표시.
    def locate_voltages(self, path: str, include_ok: bool = False) -> dict:
        d = self._load(path)
        rules = attogrid.load_rules(RULES)
        allowed = set(rules.get("allowed_voltages", []))
        items, seen = [], set()
        n_ok = n_bad = 0
        for o in d.objects:
            if o.get("entmode") != 2:
                continue
            t = o.get("entity")
            raw = o.get("text_value") if t == "TEXT" else (
                o.get("text") if t == "MTEXT" else None)
            if not isinstance(raw, str):
                continue
            clean = attogrid.clean_mtext(raw)
            pt = o.get("ins_pt")
            if not pt:
                continue
            for val, unit, _ in attogrid.parse_electrical([clean]):
                if unit.upper() != "V":
                    continue
                fv = float(val)
                norm = f"{int(fv)}V" if fv.is_integer() else f"{val}V"
                ok = norm in allowed
                if ok and not include_ok:
                    continue
                key = (norm, round(pt[0], 1), round(pt[1], 1))
                if key in seen:
                    continue
                seen.add(key)
                if ok:
                    n_ok += 1
                    detail = f"{norm}: 표준 전압(정상)"
                else:
                    n_bad += 1
                    _, detail = attogrid.explain_voltage(norm, allowed, clean)
                items.append({
                    "voltage": norm, "text": clean[:50], "x": pt[0], "y": pt[1],
                    "label": norm, "ok": ok, "detail": detail,
                    "tooltip": f"{norm} · {clean[:40]} — {detail}",
                    "color": "#3fb950" if ok else "#f85149",  # 초록=정상, 빨강=위반
                })
        return {"count": len(items), "ok": n_ok, "violations": n_bad, "items": items}

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
                 "message": f.message, "context": f.context, "detail": f.detail}
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
            "rows": [
                {"source": it.text, "translation": t, "x": it.x, "y": it.y}
                for it, t in zip(items, outs)
            ],
        }

    # --- 번역 결과 내보내기 (CSV/JSON) ---
    def export_translations(self, rows, fmt: str = "csv", out_path: str | None = None) -> dict:
        import csv
        import io
        import json as _json

        rows = rows or []
        if not out_path:
            out_path = self._save_dialog(fmt) or str(ROOT / f"translations.{fmt}")
        p = Path(out_path).expanduser()
        if p.suffix.lower() not in (".csv", ".json"):
            p = p.with_suffix("." + fmt)

        # 위치/레이어 정보가 있으면 함께 내보낸다
        has_pos = any(r.get("x") is not None for r in rows)
        if p.suffix.lower() == ".json":
            p.write_text(_json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        else:  # CSV (엑셀 한글 호환 위해 BOM)
            buf = io.StringIO()
            w = csv.writer(buf)
            head = ["원문", "번역"] + (["X", "Y"] if has_pos else [])
            w.writerow(head)
            for r in rows:
                row = [r.get("source", ""), r.get("translation", "")]
                if has_pos:
                    row += [r.get("x", ""), r.get("y", "")]
                w.writerow(row)
            p.write_text("﻿" + buf.getvalue(), encoding="utf-8")
        return {"path": str(p), "count": len(rows)}

    def _save_dialog(self, fmt: str) -> str | None:
        try:
            import webview
            win = webview.windows[0]
            r = win.create_file_dialog(
                webview.SAVE_DIALOG, save_filename=f"translations.{fmt}")
        except Exception:
            return None
        if not r:
            return None
        return r if isinstance(r, str) else r[0]


def main():
    import sys
    import webview
    # 인자로 파일 경로를 주면 UI가 자동 로드 (다이얼로그 우회용)
    default_path = None
    if len(sys.argv) > 1:
        p = Path(sys.argv[1]).expanduser()
        default_path = str(p) if p.exists() else None
        if default_path is None:
            print(f"경고: 파일을 찾을 수 없음 → {sys.argv[1]}")
    api = Api(default_path)
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
