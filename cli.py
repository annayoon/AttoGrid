#!/usr/bin/env python3
"""
attogrid CLI — DWG 도면을 읽어 텍스트 추출/번역대상 분류/전압 검증/이미지컷.

사용법:
    python cli.py inspect  <file.dwg|.json>
    python cli.py texts    <file.dwg|.json> [--translatable]
    python cli.py validate <file.dwg|.json> [--rules attogrid/rules/datacenter.json]
    python cli.py svg      <file.dwg> <out.svg>
"""
from __future__ import annotations

import argparse
import collections
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
        print(f"    [{f.severity}/{f.rule}] {f.message}  {('· ' + f.context) if f.context else ''}")


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
    s = sub.add_parser("svg"); s.add_argument("file"); s.add_argument("out"); s.set_defaults(fn=cmd_svg)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
