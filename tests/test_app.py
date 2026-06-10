"""app.Api 브리지 로직 테스트 (창/디스플레이 없이, 인메모리 도면)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import attogrid           # noqa: E402
from app import Api       # noqa: E402

# 최소 dwgread-style 도면 (LAYER 객체 + TEXT 엔티티)
FAKE = {
    "OBJECTS": [
        {"object": "LAYER", "name": "E-POWER"},
        {"object": "LAYER", "name": "E-NETWORK"},
        {"entity": "TEXT", "text_value": "额定电压 380V"},
        {"entity": "TEXT", "text_value": "CIRCUIT-A-12"},
        {"entity": "MTEXT", "text": r"{\Fxx|c0;420V\F..;母线}"},
    ]
}


def _api():
    api = Api()
    api._cache["fake"] = attogrid.Drawing(source=Path("fake"), data=FAKE, objects=FAKE["OBJECTS"])
    return api


def test_inspect_counts_layers_and_objects():
    d = _api().inspect("fake")
    assert d["objects"] == 5
    assert d["layers"] == 2


def test_texts_classifies_and_filters():
    d = _api().texts("fake", translatable_only=True)
    texts = [r["text"] for r in d["rows"]]
    assert any("额定电压" in t for t in texts)        # 중국어 = 번역대상
    assert all(t != "CIRCUIT-A-12" for t in texts)   # 식별자 = 제외


def test_validate_flags_420v():
    d = _api().validate("fake")
    assert any("420V" in f["message"] for f in d["findings"])


def test_translate_mock_applies_glossary_and_protection():
    d = _api().translate("fake", backend="mock", limit=0)
    joined = " ".join(r["translation"] for r in d["rows"])
    assert "380V" in joined          # 전압값 보존
    assert "모선" in joined           # 母线 사전 적용


def test_translate_rows_include_position():
    api = Api()
    data = {"OBJECTS": [
        {"entity": "TEXT", "entmode": 2, "text_value": "气体灭火系统", "ins_pt": [100.5, 200.25, 0]},
    ]}
    api._cache["p"] = attogrid.Drawing(source=Path("p"), data=data, objects=data["OBJECTS"])
    r = api.translate("p", backend="mock", limit=0)["rows"][0]
    assert r["x"] == 100.5 and r["y"] == 200.25

    out = api.export_translations([r], "csv", "/tmp/_attogrid_pos.csv")
    txt = Path(out["path"]).read_text(encoding="utf-8")
    assert "X,Y" in txt and "100.5" in txt


def test_export_section_translations():
    import tempfile
    # 두 시트(프레임) + 각 시트 안에 중국어 텍스트
    def rect(ox):
        return {"entity": "LWPOLYLINE", "entmode": 2, "flag": 1,
                "points": [[ox, 0], [ox + 100, 0], [ox + 100, 150], [ox, 150]]}
    data = {"OBJECTS": [
        rect(0), rect(300),
        {"entity": "TEXT", "entmode": 2, "text_value": "气体灭火系统", "ins_pt": [40, 40, 0], "height": 5},
        {"entity": "TEXT", "entmode": 2, "text_value": "额定电压", "ins_pt": [340, 40, 0], "height": 5},
    ]}
    api = Api()
    api._cache["p"] = attogrid.Drawing(source=Path("p"), data=data, objects=data["OBJECTS"])
    d = Path(tempfile.mkdtemp())
    r = api.export_section_translations("p", method="frame", backend="mock", out_dir=str(d))
    assert r["count"] == 2          # 시트 2개 → CSV 2개
    txt = Path(r["files"][0]).read_text(encoding="utf-8")
    assert "원문,번역,X,Y" in txt


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("app 테스트 통과")
