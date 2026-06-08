"""MTEXT 정제·언어분류 단위 테스트 (실파일 없이 동작)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from attogrid.text import clean_mtext, classify_language  # noqa: E402
from attogrid.validate import parse_electrical, validate   # noqa: E402


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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("모든 테스트 통과")
