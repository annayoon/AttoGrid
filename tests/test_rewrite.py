"""번역 재삽입(DXF 제자리 교체) 테스트."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ezdxf            # noqa: E402
import attogrid         # noqa: E402


def test_translate_dxf_inplace(tmp_path=None):
    import tempfile
    d = Path(tempfile.mkdtemp())
    src, out = d / "src.dxf", d / "out.dxf"

    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    msp.add_text("额定电压 380V/三相", height=0.5, dxfattribs={"insert": (0, 0)})
    msp.add_text("气体灭火系统", height=0.5, dxfattribs={"insert": (0, 2)})
    msp.add_text("CIRCUIT-A-12", height=0.5, dxfattribs={"insert": (0, 4)})
    doc.saveas(str(src))

    g = attogrid.load_glossary(
        Path(__file__).resolve().parent.parent / "attogrid" / "glossary" / "zh_ko.json"
    )
    stat = attogrid.translate_dxf(src, out, attogrid.MockTranslator(),
                                  glossary=g, target="ko", source="zh")
    assert stat["replaced"] == 3

    texts = [e.dxf.text for e in ezdxf.readfile(str(out)).modelspace().query("TEXT")]
    joined = " ".join(texts)
    assert "정격 전압" in joined        # 사전 적용
    assert "380V" in joined            # 수치 보존
    assert "가스 소화 설비" in joined    # 용어 번역
    assert "CIRCUIT-A-12" in joined    # 식별자 보존


if __name__ == "__main__":
    test_translate_dxf_inplace()
    print("PASS test_translate_dxf_inplace")
