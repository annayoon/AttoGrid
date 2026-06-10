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


def test_transformer_load_check():
    from attogrid.validate import _check_transformer_load
    # 부족: 1280kW/0.9 = 1422KVA 필요 > 1300KVA
    f = _check_transformer_load(["Pjs=1280kW", "1300KVA"], {"power_factor": 0.9})
    assert f and f[0].rule == "transformer_load"
    # 충분: 1000kW/0.9 = 1111KVA < 1300KVA
    assert not _check_transformer_load(["Pjs=1000kW", "1300KVA"], {"power_factor": 0.9})


def test_required_keywords_dict():
    rules = {"allowed_voltages": [], "required_keywords": {"接地": "접지"}, "forbidden_patterns": []}
    # 접지 없음 → 위반
    f = validate(["배전반"], rules)
    assert any(x.rule == "required_keywords" and "접지" in x.message for x in f)
    # 접지 있음 → 위반 없음
    assert not [x for x in validate(["接地 母线"], rules) if x.rule == "required_keywords"]


def test_glossary_translate_title():
    from attogrid.translate import glossary_translate
    g = {"浸没式机房": "액침 냉각 전산실", "电力系统": "전력 계통",
         "消防系统": "소방 설비", "图纸": "도면"}
    out = glossary_translate("浸没式机房电力系统、消防系统图纸", g)
    assert "액침 냉각 전산실" in out and "전력 계통" in out and "도면" in out
    assert "电" not in out and "·" in out   # 한자 사라지고 부호 변환


def test_current_breaker_check():
    from attogrid.validate import _check_current
    assert _check_current(["Ijs=4000A", "3200A/4P"], {})       # 부족
    assert not _check_current(["Ijs=2161A", "3600A/4P"], {})   # 정상


def test_redundancy_check():
    from attogrid.validate import _check_redundancy
    cfg = {"redundancy_check": {"transfer": ["ATS"], "backup": ["发电"]}}
    assert len(_check_redundancy(["배전반"], cfg)) == 2          # 둘 다 누락
    assert not _check_redundancy(["ATS", "发电机"], cfg)         # 둘 다 존재


def test_cooling_info():
    from attogrid.validate import _check_cooling
    f = _check_cooling(["制冷量22.0KW", "制冷量5.5KW"], {})
    assert f and f[0].severity == "info" and "27.5" in f[0].message


def test_explain_voltage_control_and_typo():
    from attogrid.validate import explain_voltage
    allowed = {"380V", "400V", "220V"}
    # 제어 전압
    s, d = explain_voltage("24V", allowed)
    assert "제어" in s and "제어" in d
    # 표준 근접(420V↔400V = 5%)
    s, d = explain_voltage("420V", allowed, "420V 1300KVA")
    assert "400V" in d and ("5%" in s or "5%" in d)
    # 변압기 힌트
    assert "무부하" in d


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
