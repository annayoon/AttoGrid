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
    detail: str = ""   # 무엇이/왜 틀렸는지 구체 설명


# 제어·신호용 저전압 상한(이하면 배전 전압이 아닌 제어회로로 간주)
_CONTROL_MAX = 48.0


def explain_voltage(norm: str, allowed: set, context: str = "") -> tuple[str, str]:
    """비표준 전압에 대한 (요약, 상세설명)을 만든다."""
    try:
        v = float(norm.rstrip("Vv"))
    except ValueError:
        return ("비표준 전압", f"{norm}은(는) 표준 목록에 없습니다.")

    nums = sorted({float(a.rstrip("Vv")) for a in allowed})
    nearest = min(nums, key=lambda a: abs(a - v)) if nums else v
    diff_pct = abs(nearest - v) / nearest * 100 if nearest else 0.0
    near_s = f"{int(nearest)}V" if nearest.is_integer() else f"{nearest}V"

    # 1) 제어·신호 저전압
    if v <= _CONTROL_MAX:
        return (
            f"{norm}: 제어·신호용 저전압",
            f"{norm}는 전력 배전 전압이 아니라 제어·신호용(예: 24V DC 제어, "
            f"감지기·비상정지 회로)으로 보입니다. 배전 전압 검증 대상이 아니라면 "
            f"규칙의 allowed_voltages에 제어전압을 추가하거나 제외하세요.",
        )

    # 2) 표준값에 근접 → 오타/무부하 의심
    if diff_pct <= 6:
        hint = ""
        if any(k in context for k in ("KVA", "kVA", "变压器", "TR", "변압기")):
            hint = " 변압기 표기 옆이라면 2차 무부하 전압일 수 있습니다."
        return (
            f"{norm}: 표준 {near_s}에서 {diff_pct:.0f}% 벗어남",
            f"{norm}는 표준 {near_s}와 {diff_pct:.0f}% 차이입니다. 오타이거나 공칭/"
            f"무부하 전압 차이일 수 있으니 {near_s}가 맞는지 확인하세요.{hint}",
        )

    # 3) 그 외 — 표준 배전 전압 아님
    return (
        f"{norm}: 표준 배전 전압 아님",
        f"{norm}는 허용 배전 전압({', '.join(f'{int(n)}V' for n in nums)})에 "
        f"없는 값입니다. 가장 가까운 표준은 {near_s}입니다. 도면 표기 또는 기기 "
        f"사양을 확인하세요.",
    )


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
                    summary, detail = explain_voltage(norm, allowed, src)
                    findings.append(Finding(
                        "warning", "allowed_voltages",
                        summary, src[:60], detail,
                    ))

    # 규칙 2: 필수 항목 존재 여부 (접지/이중전원 등)
    req = rules.get("required_keywords", [])
    pairs = req.items() if isinstance(req, dict) else [(k, k) for k in req]
    for term, label in pairs:
        if not any(term in s for s in texts):
            findings.append(Finding(
                "warning", "required_keywords",
                f"필수 항목 누락: {label}", "",
                f"도면에서 {label} 표기를 찾지 못했습니다. 누락 여부를 확인하세요.",
            ))

    # 규칙 3: 변압기 용량 vs 계산 부하 정합성
    findings.extend(_check_transformer_load(texts, rules))

    # 규칙 4: 전류 vs 차단기 정격
    findings.extend(_check_current(texts, rules))

    # 규칙 5: 이중화(절체장치 + 예비전원) 구성
    findings.extend(_check_redundancy(texts, rules))

    # 규칙 6: 냉방 용량(정보성)
    findings.extend(_check_cooling(texts, rules))

    # 규칙 7: 금지 패턴 (예: TODO, 미정, ???)
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


_RE_KVA = re.compile(r"(\d+\.?\d*)\s*KVA", re.I)
_RE_PJS = re.compile(r"Pjs\s*=\s*(\d+\.?\d*)\s*kW", re.I)   # 계산 부하
_RE_P = re.compile(r"\bP\s*=\s*(\d+\.?\d*)\s*kW", re.I)     # 설비 용량


def _check_transformer_load(texts: list[str], rules: dict) -> list[Finding]:
    """변압기 용량이 계산 부하를 감당하는지 점검(단일 변압기 기준 휴리스틱)."""
    if not rules.get("transformer_load_check", True):
        return []
    pf = float(rules.get("power_factor", 0.9))
    kvas, pjs, ps = [], [], []
    for t in texts:
        for m in _RE_KVA.finditer(t):
            kvas.append(float(m.group(1)))
        for m in _RE_PJS.finditer(t):
            pjs.append((float(m.group(1)), t))
        for m in _RE_P.finditer(t):
            ps.append((float(m.group(1)), t))
    if not kvas:
        return []
    loads = pjs or ps          # 계산 부하 우선, 없으면 설비 용량
    if not loads:
        return []
    load_val, load_src = max(loads, key=lambda x: x[0])
    max_tr = max(kvas)
    required = load_val / pf
    if required > max_tr:
        over = (required / max_tr - 1) * 100
        return [Finding(
            "warning", "transformer_load",
            f"변압기 용량 부족 가능성: 부하 {load_val:.0f}kW → 약 {required:.0f}KVA 필요 "
            f"(최대 변압기 {max_tr:.0f}KVA)",
            load_src[:60],
            f"계산 부하 {load_val:.0f}kW를 역률 {pf}로 환산하면 약 {required:.0f}KVA가 "
            f"필요한데, 도면 최대 변압기 용량은 {max_tr:.0f}KVA로 약 {over:.0f}% 부족합니다. "
            f"단일 변압기 공급 기준이며, 이중화·분산 공급이면 변압기별 부하 배분을 확인하세요.",
        )]
    return []


_RE_IJS = re.compile(r"Ijs\s*=\s*(\d+\.?\d*)\s*A", re.I)        # 계산 전류
_RE_IN = re.compile(r"\bIn\s*=\s*(\d+\.?\d*)\s*A", re.I)        # 차단기 정격
_RE_BRK = re.compile(r"(\d+\.?\d*)\s*A\s*/\s*\d+\s*P", re.I)    # 3200A/4P
_RE_COOL = re.compile(r"制冷量\s*(\d+\.?\d*)\s*KW", re.I)        # 냉방 용량


def _check_current(texts: list[str], rules: dict) -> list[Finding]:
    """계산 전류가 차단기/보호기기 정격을 넘지 않는지 점검(최대값 기준)."""
    if not rules.get("current_check", True):
        return []
    ijs, brks = [], []
    for t in texts:
        for m in _RE_IJS.finditer(t):
            ijs.append((float(m.group(1)), t))
        for m in _RE_IN.finditer(t):
            brks.append(float(m.group(1)))
        for m in _RE_BRK.finditer(t):
            brks.append(float(m.group(1)))
    if not ijs or not brks:
        return []
    max_i, src = max(ijs, key=lambda x: x[0])
    max_b = max(brks)
    if max_i > max_b:
        return [Finding(
            "warning", "current_breaker",
            f"차단기 정격 부족 가능성: 계산전류 {max_i:.0f}A > 최대 차단기 {max_b:.0f}A",
            src[:60],
            f"계산 전류 {max_i:.0f}A가 도면 최대 차단기 정격 {max_b:.0f}A를 초과합니다. "
            f"보호기기 정격(In ≥ Ijs)과 케이블 허용전류를 확인하세요.",
        )]
    return []


def _check_redundancy(texts: list[str], rules: dict) -> list[Finding]:
    """이중화 구성(절체장치 + 예비전원) 표기 존재 점검."""
    cfg = rules.get("redundancy_check")
    if not cfg:
        return []
    transfer = cfg.get("transfer", ["ATS", "双电源"])
    backup = cfg.get("backup", ["发电", "UPS", "备用"])
    out = []
    if not any(k in s for s in texts for k in transfer):
        out.append(Finding(
            "warning", "redundancy", "이중화 절체장치 미확인", "",
            f"절체장치({'/'.join(transfer)}) 표기를 찾지 못했습니다. "
            f"이중전원 자동절체(ATS 등) 구성을 확인하세요.",
        ))
    if not any(k in s for s in texts for k in backup):
        out.append(Finding(
            "warning", "redundancy", "예비/비상 전원 미확인", "",
            f"예비 전원({'/'.join(backup)}) 표기를 찾지 못했습니다. "
            f"발전기·UPS 등 백업 전원 구성을 확인하세요.",
        ))
    return out


def _check_cooling(texts: list[str], rules: dict) -> list[Finding]:
    """냉방 용량 요약(정보성). 도면 수량/배치는 수동 확인 필요."""
    if not rules.get("cooling_check", True):
        return []
    cool = sum(float(m.group(1)) for t in texts for m in _RE_COOL.finditer(t))
    if cool <= 0:
        return []
    loads = [float(m.group(1)) for t in texts for m in _RE_PJS.finditer(t)]
    it = max(loads) if loads else 0
    detail = (f"도면에 표기된 냉방 용량(制冷量) 합계는 약 {cool:.1f}kW입니다. "
              f"이는 서로 다른 기종 정격의 단순 합이며 실제 설치 수량은 도면에서 확인해야 합니다.")
    if it:
        detail += (f" 전기 계산부하 최대 {it:.0f}kW가 발열로 환산된다고 보면 냉방 "
                   f"여력을 비교 검토하세요.")
    return [Finding(
        "info", "cooling",
        f"냉방 용량 합계 약 {cool:.1f}kW (수동 확인 권장)", "", detail,
    )]
