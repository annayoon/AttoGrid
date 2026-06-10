"""
전압/전기 구성 검증 규칙 엔진.

규칙은 attogrid/rules/*.json 으로 외부화한다(도면 작성 표준이 회사마다 다르므로).
여기서는 추출된 텍스트에서 전압/전류/전력 값을 파싱하고 규칙에 대조한다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# 전압/전류/전력/용량 토큰.
# 뒤에 ASCII 영문이 오는 경우만 배제(VAC 등)하고, 한자/공백/구두점은 허용.
# 중국어 도면의 "380V电源"처럼 단위에 한자가 바로 붙는 경우도 탐지하기 위함.
_RE_ELEC = re.compile(
    r"(?P<val>\d+\.?\d*)\s*(?P<unit>kVA|KVA|kV|KV|VAC|VDC|V|kW|KW|W|MPa|A)(?![A-Za-z])"
)


@dataclass
class Finding:
    severity: str   # "error" | "warning" | "info"
    rule: str
    message: str
    context: str = ""


def parse_electrical(texts) -> list[tuple[str, str, str]]:
    """(값, 단위, 원문) 목록을 반환."""
    out = []
    for s in texts:
        for m in _RE_ELEC.finditer(s):
            out.append((m.group("val"), m.group("unit"), s))
    return out


def load_rules(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(texts: list[str], rules: dict) -> list[Finding]:
    """텍스트 목록을 규칙에 대조해 위반 사항을 반환."""
    findings: list[Finding] = []
    elec = parse_electrical(texts)

    # 규칙 1: 허용 전압 레벨 (값 기준 중복 제거)
    allowed = set(rules.get("allowed_voltages", []))
    if allowed:
        seen_volts = set()
        for val, unit, src in elec:
            if unit.upper() == "V":
                norm = f"{int(float(val))}V" if float(val).is_integer() else f"{val}V"
                if norm not in allowed and norm not in seen_volts:
                    seen_volts.add(norm)
                    findings.append(Finding(
                        "warning", "allowed_voltages",
                        f"비표준 전압 {norm} (허용: {sorted(allowed)})",
                        src[:60],
                    ))

    # 규칙 2: 필수 키워드 존재 여부 (예: 이중전원, 接地 등)
    for kw in rules.get("required_keywords", []):
        if not any(kw in s for s in texts):
            findings.append(Finding(
                "warning", "required_keywords",
                f"필수 키워드 누락: {kw!r}",
            ))

    # 규칙 3: 금지 패턴 (예: TODO, 미정, ???)
    for pat in rules.get("forbidden_patterns", []):
        rx = re.compile(pat)
        for s in texts:
            if rx.search(s):
                findings.append(Finding(
                    "error", "forbidden_patterns",
                    f"금지 패턴 {pat!r} 발견", s[:60],
                ))
                break

    return findings
