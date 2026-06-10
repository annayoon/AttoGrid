#!/usr/bin/env python3
"""
attogrid CLI — DWG 도면을 읽어 텍스트 추출/번역대상 분류/전압 검증/이미지컷.

사용법:
    python cli.py inspect  <file.dwg|.json>
    python cli.py texts    <file.dwg|.json> [--translatable]
    python cli.py validate <file.dwg|.json> [--rules attogrid/rules/datacenter.json]
    python cli.py translate <file.dwg|.json> [--to ko] [--limit N] [--mock] [--out map.json]
    python cli.py rewrite  <file.dxf> <out.dxf> [--backend argos] [--to ko]
    python cli.py image    <file.dwg|.json> <out.png|.svg>
    python cli.py svg      <file.dwg> <out.svg>
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import attogrid


def cmd_inspect(args):
    d = attogrid.read(args.file)
    print(f"파일: {args.file}")
    print(f"객체 수: {len(d.objects)}")
    kinds = collections.Counter(o.get("entity") or o.get("object") or "?" for o in d.objects)
    print("엔티티 분포(상위 15):")
    for k, n in kinds.most_common(15):
        print(f"  {str(k):18} {n}")
    print(f"레이어: {len(d.layers)}개")


def cmd_texts(args):
    d = attogrid.read(args.file)
    items = attogrid.extract_texts(d)
    dist = collections.Counter(i.lang for i in items)
    print(f"텍스트 {len(items)}개 | 언어분포: {dict(dist)}")
    for it in items:
        if args.translatable and not it.translatable:
            continue
        tag = "T" if it.translatable else "-"
        print(f"  [{it.lang}|{tag}] {it.text[:70]}")


def cmd_validate(args):
    d = attogrid.read(args.file)
    items = attogrid.extract_texts(d)
    texts = [i.text for i in items]
    rules = attogrid.load_rules(args.rules)
    findings = attogrid.validate(texts, rules)
    print(f"규칙셋: {rules.get('name')}")
    if not findings:
        print("  ✓ 위반 없음")
        return
    print(f"  ⚠ 위반 {len(findings)}건:")
    for f in findings:
        print(f"    [{f.severity}] {f.message}  {('· 도면: ' + f.context) if f.context else ''}")
        if f.detail:
            print(f"        → {f.detail}")


def cmd_translate(args):
    d = attogrid.read(args.file)
    items = attogrid.extract_texts(d)
    targets = [i for i in items if i.translatable]
    if args.limit:
        targets = targets[:args.limit]
    glossary = attogrid.load_glossary(args.glossary) if args.glossary else {}

    backend = "mock" if args.mock else args.backend
    if backend == "mock":
        translator = attogrid.MockTranslator()
        print("[mock] 실제 번역 없이 보호/사전 처리만 적용합니다.")
    elif backend == "argos":
        translator = attogrid.ArgosTranslator()  # 오프라인·무료
        print("[argos] 오프라인 오픈소스 번역 (영어 경유 pivot).")
    else:
        translator = attogrid.DeepLTranslator()  # DEEPL_API_KEY 필요
        print("[deepl] DeepL API 번역.")

    cache = attogrid.TranslationCache(Path(args.cache)).load() if args.cache else None
    srcs = [t.text for t in targets]
    outs = attogrid.translate_texts(
        srcs, translator, glossary=glossary,
        target=args.to, source="zh", cache=cache,
    )

    print(f"번역 대상 {len(targets)}건 (고유 {len(set(srcs))}건)")
    for src, tr in list(zip(srcs, outs))[:args.show]:
        print(f"  · {src[:40]}\n    → {tr[:60]}")

    if args.out:
        rows = [{"source": s, "translation": t} for s, t in zip(srcs, outs)]
        if args.out.lower().endswith(".csv"):
            import csv
            import io
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["원문", "번역"])
            for r in rows:
                w.writerow([r["source"], r["translation"]])
            Path(args.out).write_text("﻿" + buf.getvalue(), encoding="utf-8")
        else:
            Path(args.out).write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {args.out} ({len(rows)}건)")


def cmd_rewrite(args):
    glossary = attogrid.load_glossary(args.glossary) if args.glossary else {}
    if args.backend == "mock":
        tr = attogrid.MockTranslator()
    elif args.backend == "deepl":
        tr = attogrid.DeepLTranslator()
    else:
        tr = attogrid.ArgosTranslator()
    cache = attogrid.TranslationCache(Path(args.cache)).load() if args.cache else None
    stat = attogrid.translate_dxf(
        args.file, args.out, tr, glossary=glossary,
        target=args.to, source="zh", cache=cache,
    )
    print(f"번역 재삽입 완료: {stat['replaced']}/{stat['entities']}건 → {stat['out']}")


def cmd_image(args):
    d = attogrid.read(args.file)
    if args.out.lower().endswith(".svg"):
        attogrid.render.json_to_svg(d, out_path=args.out)
    else:
        attogrid.render.json_to_png(d, args.out)
    print(f"이미지 저장: {args.out}")


def cmd_svg(args):
    out = attogrid.render.to_svg(args.file, args.out)
    print(f"SVG 저장: {out}")


def main():
    p = argparse.ArgumentParser(prog="attogrid")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("inspect"); s.add_argument("file"); s.set_defaults(fn=cmd_inspect)
    s = sub.add_parser("texts"); s.add_argument("file")
    s.add_argument("--translatable", action="store_true"); s.set_defaults(fn=cmd_texts)
    s = sub.add_parser("validate"); s.add_argument("file")
    s.add_argument("--rules", default="attogrid/rules/datacenter.json"); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("translate"); s.add_argument("file")
    s.add_argument("--to", default="ko")
    s.add_argument("--glossary", default="attogrid/glossary/zh_ko.json")
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--show", type=int, default=15)
    s.add_argument("--backend", choices=["deepl", "argos", "mock"], default="deepl")
    s.add_argument("--mock", action="store_true")
    s.add_argument("--cache", default=".attogrid_cache.json")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_translate)
    s = sub.add_parser("rewrite"); s.add_argument("file"); s.add_argument("out")
    s.add_argument("--to", default="ko")
    s.add_argument("--backend", choices=["deepl", "argos", "mock"], default="argos")
    s.add_argument("--glossary", default="attogrid/glossary/zh_ko.json")
    s.add_argument("--cache", default=".attogrid_cache.json")
    s.set_defaults(fn=cmd_rewrite)
    s = sub.add_parser("image"); s.add_argument("file"); s.add_argument("out")
    s.set_defaults(fn=cmd_image)
    s = sub.add_parser("svg"); s.add_argument("file"); s.add_argument("out"); s.set_defaults(fn=cmd_svg)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
