#!/usr/bin/env python3
"""
AttoGrid 웹 서버 (Flask).

사내 서버에서 팀 전원이 브라우저로 접속해 사용.
Ollama(무료 로컬 AI)를 통해 중국어→한국어 번역 지원.

실행:
    pip install flask
    python web_app.py                       # 기본: 0.0.0.0:5000
    python web_app.py --port 8080           # 포트 변경
    python web_app.py --host 127.0.0.1      # 로컬만 허용

접속:
    사내 서버: http://<서버_IP>:5000
    로컬:     http://localhost:5000
"""
from __future__ import annotations

import collections
import io
import json
import os
import tempfile
import threading
import zipfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

import attogrid

ROOT     = Path(__file__).resolve().parent
GLOSSARY = ROOT / "attogrid" / "glossary" / "zh_ko.json"
RULES    = ROOT / "attogrid" / "rules"    / "datacenter.json"
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ── Flask 앱 ──────────────────────────────────────────────────────
app = Flask(__name__)

# ── 인메모리 캐시 (Drawing 파싱 결과 + 연산 결과) ─────────────────
_dcache:  dict[str, attogrid.Drawing] = {}  # path → Drawing
_rcache:  dict[tuple, object]         = {}  # (path, op, ...) → 결과
_rcache_lock = threading.Lock()


def _load(path: str) -> attogrid.Drawing:
    if path not in _dcache:
        _dcache[path] = attogrid.read(path)
    return _dcache[path]


def _rcget(key):
    with _rcache_lock:
        return _rcache.get(key)


def _rcset(key, value):
    with _rcache_lock:
        _rcache[key] = value
    return value


def _warm(path: str) -> None:
    """백그라운드에서 SVG·extrude 미리 계산."""
    def _do():
        try:
            d = _load(path)
            svg_key = (path, "svg", 50000)
            if _rcget(svg_key) is None:
                svg = attogrid.render.json_to_svg(d, max_count=50000, width=1400)
                _rcset(svg_key, {"svg": svg, "polylines": svg.count("<polyline")})
            ext_key = (path, "extrude")
            if _rcget(ext_key) is None:
                _rcset(ext_key, attogrid.extrude(d))
        except Exception:
            pass
    threading.Thread(target=_do, daemon=True).start()


def _translator(backend: str):
    if backend == "mock":
        return attogrid.MockTranslator()
    if backend == "deepl":
        return attogrid.DeepLTranslator()
    if backend == "ollama":
        return attogrid.OllamaTranslator()
    return attogrid.ArgosTranslator()


def _err(msg: str, code: int = 500):
    return jsonify({"error": msg}), code


# ── 정적 파일 ────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(ROOT / "ui", "index.html")


@app.route("/<path:filename>")
def ui_static(filename):
    return send_from_directory(ROOT / "ui", filename)


# ── 파일 업로드 / 목록 ────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return _err("파일이 없습니다", 400)
    f = request.files["file"]
    if not f.filename:
        return _err("파일명이 없습니다", 400)
    dest = UPLOAD_DIR / Path(f.filename).name
    f.save(str(dest))
    return jsonify({"path": str(dest), "name": dest.name})


@app.route("/api/files", methods=["GET"])
def api_files():
    files = sorted(UPLOAD_DIR.glob("*.json")) + sorted(UPLOAD_DIR.glob("*.dwg"))
    return jsonify({"files": [{"name": p.name, "path": str(p)} for p in files]})


# ── 공통 API ─────────────────────────────────────────────────────
@app.route("/api/default_path", methods=["GET", "POST"])
def api_default_path():
    # 웹 모드에서는 URL 파라미터로 기본 파일 지정 가능 (?file=path)
    p = request.args.get("file") or (request.json or {}).get("file")
    return jsonify(p or None)


@app.route("/api/inspect", methods=["POST"])
def api_inspect():
    data = request.get_json(force=True)
    path = data.get("path", "")
    try:
        d = _load(path)
        _warm(path)
        kinds = collections.Counter(
            o.get("entity") or o.get("object") or "?" for o in d.objects
        )
        return jsonify({
            "path": path,
            "objects": len(d.objects),
            "layers": len(d.layers),
            "entities": kinds.most_common(15),
        })
    except Exception as e:
        return _err(str(e))


@app.route("/api/render", methods=["POST"])
def api_render():
    data    = request.get_json(force=True)
    path      = data.get("path", "")
    max_count = data.get("max_count", 50000)
    highlights = data.get("highlights")
    boxes      = data.get("boxes")
    try:
        d = _load(path)
        use_cache = not highlights and not boxes
        key = (path, "svg", max_count)
        if use_cache:
            cached = _rcget(key)
            if cached is not None:
                return jsonify(cached)
        svg = attogrid.render.json_to_svg(
            d, max_count=max_count, width=1400, highlights=highlights, boxes=boxes)
        result = {"svg": svg, "polylines": svg.count("<polyline")}
        if use_cache:
            _rcset(key, result)
        return jsonify(result)
    except Exception as e:
        return _err(str(e))


@app.route("/api/texts", methods=["POST"])
def api_texts():
    data = request.get_json(force=True)
    path             = data.get("path", "")
    translatable_only = data.get("translatable_only", False)
    limit            = data.get("limit", 300)
    try:
        d = _load(path)
        items = attogrid.extract_texts(d)
        dist = collections.Counter(i.lang for i in items)
        rows = [
            {"lang": i.lang, "translatable": i.translatable, "text": i.text}
            for i in items
            if not translatable_only or i.translatable
        ][:limit]
        return jsonify({"total": len(items), "dist": dict(dist), "rows": rows})
    except Exception as e:
        return _err(str(e))


@app.route("/api/validate", methods=["POST"])
def api_validate():
    path = request.get_json(force=True).get("path", "")
    try:
        d = _load(path)
        texts = [i.text for i in attogrid.extract_texts(d)]
        rules = attogrid.load_rules(RULES)
        findings = attogrid.validate(texts, rules)
        return jsonify({
            "ruleset": rules.get("name"),
            "count": len(findings),
            "findings": [
                {"severity": f.severity, "rule": f.rule,
                 "message": f.message, "context": f.context, "detail": f.detail}
                for f in findings
            ],
        })
    except Exception as e:
        return _err(str(e))


@app.route("/api/model3d", methods=["POST"])
def api_model3d():
    path = request.get_json(force=True).get("path", "")
    try:
        key = (path, "extrude")
        cached = _rcget(key)
        if cached is not None:
            return jsonify(cached)
        d = _load(path)
        return jsonify(_rcset(key, attogrid.extrude(d)))
    except Exception as e:
        return _err(str(e))


@app.route("/api/locate_voltages", methods=["POST"])
def api_locate_voltages():
    data       = request.get_json(force=True)
    path       = data.get("path", "")
    include_ok = data.get("include_ok", False)
    try:
        d = _load(path)
        rules   = attogrid.load_rules(RULES)
        allowed = set(rules.get("allowed_voltages", []))
        items, seen = [], set()
        n_ok = n_bad = 0
        for o in d.objects:
            if o.get("entmode") != 2:
                continue
            t   = o.get("entity")
            raw = (o.get("text_value") if t == "TEXT"
                   else o.get("text")  if t == "MTEXT" else None)
            if not isinstance(raw, str):
                continue
            clean = attogrid.clean_mtext(raw)
            pt    = o.get("ins_pt")
            if not pt:
                continue
            for val, unit, _ in attogrid.parse_electrical([clean]):
                if unit.upper() != "V":
                    continue
                fv   = float(val)
                norm = f"{int(fv)}V" if fv.is_integer() else f"{val}V"
                ok   = norm in allowed
                if ok and not include_ok:
                    continue
                key  = (norm, round(pt[0], 1), round(pt[1], 1))
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
                    "color": "#3fb950" if ok else "#f85149",
                })
        return jsonify({"count": len(items), "ok": n_ok, "violations": n_bad, "items": items})
    except Exception as e:
        return _err(str(e))


@app.route("/api/translate", methods=["POST"])
def api_translate():
    data    = request.get_json(force=True)
    path    = data.get("path", "")
    backend = data.get("backend", "argos")
    limit   = data.get("limit", 50)
    try:
        d = _load(path)
        items = [i for i in attogrid.extract_texts(d) if i.translatable]
        if limit:
            items = items[:int(limit)]
        glossary = attogrid.load_glossary(GLOSSARY)
        tr   = _translator(backend)
        srcs = [i.text for i in items]
        outs = attogrid.translate_texts(srcs, tr, glossary=glossary,
                                        target="ko", source="zh")
        return jsonify({
            "backend": backend,
            "count": len(srcs),
            "rows": [
                {"source": it.text, "translation": t, "x": it.x, "y": it.y}
                for it, t in zip(items, outs)
            ],
        })
    except Exception as e:
        return _err(str(e))


@app.route("/api/render_translated", methods=["POST"])
def api_render_translated():
    data      = request.get_json(force=True)
    path      = data.get("path", "")
    backend   = data.get("backend", "glossary")
    max_count = data.get("max_count", 50000)
    try:
        d = _load(path)
        items    = [it for it in attogrid.extract_texts(d)
                    if it.translatable and it.x is not None]
        glossary = attogrid.load_glossary(GLOSSARY)
        if backend == "glossary":
            outs = [attogrid.glossary_translate(it.text, glossary) for it in items]
        else:
            tr   = _translator(backend)
            outs = attogrid.translate_texts(
                [it.text for it in items], tr,
                glossary=glossary, target="ko", source="zh")
        texts = [{"x": it.x, "y": it.y, "height": it.height, "text": t}
                 for it, t in zip(items, outs) if t]
        svg = attogrid.render.json_to_svg(
            d, max_count=max_count, width=1400, texts=texts)
        return jsonify({"svg": svg, "texts": len(texts), "backend": backend})
    except Exception as e:
        return _err(str(e))


@app.route("/api/partition", methods=["POST"])
def api_partition():
    data   = request.get_json(force=True)
    path   = data.get("path", "")
    method = data.get("method", "auto")
    rows   = data.get("rows", 2)
    cols   = data.get("cols", 2)
    try:
        key = (path, "partition", method, rows, cols)
        cached = _rcget(key)
        if cached is not None:
            return jsonify(cached)
        from attogrid.partition import section_title
        d        = _load(path)
        secs     = attogrid.partition(d, method=method, rows=rows, cols=cols)
        items    = attogrid.extract_texts(d)
        rules    = attogrid.load_rules(RULES)
        glossary = attogrid.load_glossary(GLOSSARY)
        for s in secs:
            b      = s["bounds"]
            inside = [it for it in items if it.x is not None
                      and b[0] <= it.x <= b[2] and b[1] <= it.y <= b[3]]
            findings  = attogrid.validate([it.text for it in inside], rules)
            zh_title  = section_title(d, b) or s["label"]
            s["title_zh"] = zh_title
            s["title"]    = attogrid.glossary_translate(zh_title, glossary)
            s["texts"]       = len(inside)
            s["translatable"]= sum(1 for it in inside if it.translatable)
            s["violations"]  = sum(1 for f in findings if f.severity != "info")
        result = {"method": method, "count": len(secs), "sections": secs}
        return jsonify(_rcset(key, result))
    except Exception as e:
        return _err(str(e))


# ── 파일 다운로드 엔드포인트 ──────────────────────────────────────
@app.route("/api/export_image", methods=["POST"])
def api_export_image():
    data        = request.get_json(force=True)
    path        = data.get("path", "")
    fmt         = data.get("fmt", "png")
    with_markers = data.get("markers", False)
    try:
        d = _load(path)
        highlights = None
        if with_markers:
            rules   = attogrid.load_rules(RULES)
            allowed = set(rules.get("allowed_voltages", []))
            highlights = []
            for o in d.objects:
                if o.get("entmode") != 2:
                    continue
                t = o.get("entity")
                raw = (o.get("text_value") if t == "TEXT"
                       else o.get("text") if t == "MTEXT" else None)
                if not isinstance(raw, str):
                    continue
                clean = attogrid.clean_mtext(raw)
                pt = o.get("ins_pt")
                if not pt:
                    continue
                for val, unit, _ in attogrid.parse_electrical([clean]):
                    if unit.upper() != "V":
                        continue
                    fv   = float(val)
                    norm = f"{int(fv)}V" if fv.is_integer() else f"{val}V"
                    if norm not in allowed:
                        highlights.append({
                            "x": pt[0], "y": pt[1], "label": norm,
                            "color": "#f85149",
                        })

        suffix = f".{fmt}"
        fd, tmp = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            if fmt == "svg":
                attogrid.render.json_to_svg(d, out_path=tmp, highlights=highlights)
                mime = "image/svg+xml"
            else:
                attogrid.render.json_to_png(d, tmp, highlights=highlights)
                mime = "image/png"
            stem = Path(path).stem
            return send_file(tmp, as_attachment=True,
                             download_name=f"{stem}.{fmt}", mimetype=mime)
        except Exception:
            os.unlink(tmp)
            raise
    except Exception as e:
        return _err(str(e))


@app.route("/api/export_translations", methods=["POST"])
def api_export_translations():
    data = request.get_json(force=True)
    rows = data.get("rows", [])
    fmt  = data.get("fmt", "csv")
    try:
        if fmt == "json":
            content = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
            mime    = "application/json"
            fname   = "translations.json"
        else:
            import csv
            buf = io.StringIO()
            w   = csv.writer(buf)
            has_pos = any(r.get("x") is not None for r in rows)
            w.writerow(["원문", "번역"] + (["X", "Y"] if has_pos else []))
            for r in rows:
                row = [r.get("source", ""), r.get("translation", "")]
                if has_pos:
                    row += [r.get("x", ""), r.get("y", "")]
                w.writerow(row)
            content = ("﻿" + buf.getvalue()).encode("utf-8")
            mime    = "text/csv; charset=utf-8"
            fname   = "translations.csv"
        return send_file(io.BytesIO(content), as_attachment=True,
                         download_name=fname, mimetype=mime)
    except Exception as e:
        return _err(str(e))


@app.route("/api/export_sections", methods=["POST"])
def api_export_sections():
    data        = request.get_json(force=True)
    path        = data.get("path", "")
    method      = data.get("method", "auto")
    fmt         = data.get("fmt", "png")
    with_markers = data.get("markers", False)
    rows        = data.get("rows", 2)
    cols        = data.get("cols", 2)
    try:
        from attogrid.partition import section_title
        d    = _load(path)
        secs = attogrid.partition(d, method=method, rows=rows, cols=cols)
        if not secs:
            return _err("구획 없음", 400)
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, s in enumerate(secs, 1):
                b     = tuple(s["bounds"])
                title = section_title(d, b) or s["label"]
                safe  = "".join(c for c in title if c.isalnum())[:20] or s["label"]
                fname = f"{i:02d}_{safe}.{fmt}"
                fd, tmp = tempfile.mkstemp(suffix=f".{fmt}")
                os.close(fd)
                try:
                    if fmt == "svg":
                        attogrid.render.json_to_svg(d, out_path=tmp, bounds=b)
                    else:
                        attogrid.render.json_to_png(d, tmp, bounds=b)
                    zf.write(tmp, fname)
                except Exception:
                    pass
                finally:
                    try: os.unlink(tmp)
                    except: pass
        zip_buf.seek(0)
        return send_file(zip_buf, as_attachment=True,
                         download_name="sections.zip", mimetype="application/zip")
    except Exception as e:
        return _err(str(e))


@app.route("/api/export_section_translations", methods=["POST"])
def api_export_section_translations():
    data    = request.get_json(force=True)
    path    = data.get("path", "")
    method  = data.get("method", "auto")
    backend = data.get("backend", "argos")
    rows    = data.get("rows", 2)
    cols    = data.get("cols", 2)
    try:
        import csv
        from attogrid.partition import section_title
        d     = _load(path)
        secs  = attogrid.partition(d, method=method, rows=rows, cols=cols)
        if not secs:
            return _err("구획 없음", 400)
        items    = [it for it in attogrid.extract_texts(d)
                    if it.translatable and it.x is not None]
        glossary = attogrid.load_glossary(GLOSSARY)
        tr       = _translator(backend)
        zip_buf  = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, s in enumerate(secs, 1):
                b      = s["bounds"]
                inside = [it for it in items
                          if b[0] <= it.x <= b[2] and b[1] <= it.y <= b[3]]
                if not inside:
                    continue
                srcs = [it.text for it in inside]
                outs = attogrid.translate_texts(
                    srcs, tr, glossary=glossary, target="ko", source="zh")
                title = section_title(d, b) or s["label"]
                safe  = "".join(c for c in title if c.isalnum())[:20] or s["label"]
                buf   = io.StringIO()
                w     = csv.writer(buf)
                w.writerow(["원문", "번역", "X", "Y"])
                for it, t in zip(inside, outs):
                    w.writerow([it.text, t, it.x, it.y])
                zf.writestr(f"{i:02d}_{safe}.csv", "﻿" + buf.getvalue())
        zip_buf.seek(0)
        return send_file(zip_buf, as_attachment=True,
                         download_name="section_translations.zip",
                         mimetype="application/zip")
    except Exception as e:
        return _err(str(e))


# ── Ollama 상태 확인 ──────────────────────────────────────────────
@app.route("/api/ollama_status", methods=["GET"])
def api_ollama_status():
    """LLM 서버 연결 및 모델 목록 확인 (Ollama / vLLM / OpenAI 호환)."""
    import urllib.request as _ur
    host = os.environ.get("OLLAMA_HOST", "http://10.0.98.99:8000").rstrip("/")
    try:
        with _ur.urlopen(f"{host}/v1/models", timeout=3) as r:
            data = json.loads(r.read())
        models = [m["id"] for m in data.get("data", [])]
        return jsonify({"ok": True, "host": host, "models": models})
    except Exception as e:
        return jsonify({"ok": False, "host": host, "error": str(e)})


# ── 서버 실행 ─────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="AttoGrid 웹 서버")
    parser.add_argument("--host",  default="0.0.0.0",
                        help="바인딩 주소 (기본: 0.0.0.0 — 사내 전체 접근)")
    parser.add_argument("--port",  type=int, default=5000,
                        help="포트 번호 (기본: 5000)")
    parser.add_argument("--debug", action="store_true",
                        help="Flask 디버그 모드 (개발용)")
    args = parser.parse_args()

    print("=" * 60)
    print("  AttoGrid 웹 서버 (by ATTO Research)")
    print(f"  주소: http://{args.host}:{args.port}")
    print(f"  업로드: {UPLOAD_DIR}")
    print(f"  Ollama 번역: python web_app.py  →  번역 탭에서 'Ollama' 선택")
    print("=" * 60)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
