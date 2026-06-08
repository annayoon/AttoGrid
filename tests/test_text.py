"""MTEXT 정제·언어분류 단위 테스트 (실파일 없이 동작)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from attogrid.text import clean_mtext, classify_language  # noqa: E402
from attogrid.validate import parse_electrical, validate   # noqa: E402
from attogrid.translate import (                            # noqa: E402
    mask, unmask, translate_texts, MockTranslator,
)


def test_clean_mtext_strips_font_codes():
    raw = r"{\Fxd-hzs,xd-hztxt|c0;220V\Fxd-hzs,xd-hztxt|c134;电源线}"
    assert clean_mtext(raw) == "220V电源线"


def test_classify_language():
    assert classify_language("주 배전반") == "ko"
    assert classify_language("气体灭火") == "zh"
    assert classify_language("CIRCUIT-A-12") == "en"


def test_parse_electrical():
    found = parse_electrical(["额定电压AC 380V", "制冷量22.0KW", "ATS 3200A/4P"])
    units = {u for _, u, _ in found}
    assert "V" in units and "KW" in units and "A" in units


def test_validate_flags_nonstandard_voltage():
    rules = {"allowed_voltages": ["380V", "220V"], "forbidden_patterns": []}
    findings = validate(["额定电压 210V"], rules)
    assert any(f.rule == "allowed_voltages" for f in findings)


def test_mask_protects_identifiers_and_units():
    # 식별자/전압값은 <x>로 보호되어야 한다
    m = mask("额定电压 380V 接 CIRCUIT-A-12", {})
    assert "<x>380V</x>" in m
    assert "<x>CIRCUIT-A-12</x>" in m


def test_glossary_injects_korean_term():
    g = {"额定电压": "정격 전압"}
    m = mask("额定电压 AC380V", g)
    assert "<x>정격 전압</x>" in m
    assert "<x>AC380V</x>" in m or "<x>380V</x>" in m


def test_roundtrip_preserves_protected_and_glossary():
    # MockTranslator(식별 변환) 기준: 보호 토큰/사전 용어가 살아남아야 한다
    g = {"额定电压": "정격 전압", "三相": "3상"}
    out = translate_texts(["额定电压AC 380V/三相"], MockTranslator(), glossary=g)
    assert "정격 전압" in out[0]
    assert "3상" in out[0]
    assert "380V" in out[0]            # 전압값 보존
    assert "<x>" not in out[0]          # 태그는 제거됨


def test_translate_dedupes_identical_sources():
    calls = {"n": 0}

    class Counting(MockTranslator):
        def translate_batch(self, texts, target, source=None):
            calls["n"] += len(texts)
            return list(texts)

    translate_texts(["220V", "220V", "220V"], Counting())
    assert calls["n"] == 1             # 중복 1건만 번역


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("모든 테스트 통과")
