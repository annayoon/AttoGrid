"""
DWG/DXF 처리 파이프라인 검증.
입력 DXF를 읽어:
  1) 텍스트 추출 (번역 대상 식별, 식별자 제외 규칙 포함)
  2) 전압/구성 검증 (규칙 엔진)
  3) 이미지컷 PNG 렌더링
"""
import re
import sys
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt

path = sys.argv[1] if len(sys.argv) > 1 else "sample.dxf"
doc = ezdxf.readfile(path)
msp = doc.modelspace()

print(f"=== 입력: {path} ===")
print(f"레이어: {[l.dxf.name for l in doc.layers]}\n")

# ---------- 1) 텍스트 추출 (번역 대상) ----------
print("=== 1) 텍스트 추출 (번역 대상) ===")
# 식별자/회로명 패턴은 번역 제외
EXCLUDE = re.compile(r"^[A-Z0-9][A-Z0-9\-_/]*$")  # 예: CIRCUIT-A-12, R-01
texts = []
for e in msp.query("TEXT MTEXT"):
    s = e.dxf.text if e.dxftype() == "TEXT" else e.text
    s = s.strip()
    if not s:
        continue
    translatable = not EXCLUDE.match(s)
    texts.append((s, translatable))
    flag = "번역대상" if translatable else "제외(식별자)"
    print(f"  [{flag}] {s!r}")
print()

# ---------- 2) 전압/구성 검증 (규칙 엔진) ----------
print("=== 2) 전압/구성 검증 ===")
ALLOWED_VOLTAGES = {"480V", "208V", "120V"}  # 데이터센터 표준 레벨
issues = []
pdus = []
for ins in msp.query("INSERT"):
    if ins.dxf.name != "PDU":
        continue
    attrs = {a.dxf.tag: a.dxf.text for a in ins.attribs}
    pdus.append(attrs)
    v = attrs.get("VOLTAGE", "")
    if v not in ALLOWED_VOLTAGES:
        issues.append(f"[전압] {attrs.get('NAME','?')}: 비표준 전압 {v!r} "
                      f"(허용: {sorted(ALLOWED_VOLTAGES)})")

# A/B 이중화 검증: PDU 이름이 PDU-A* / PDU-B* 짝을 이뤄야 함
def base(name):  # PDU-A2 -> 2
    m = re.match(r"PDU-([AB])(\d+)", name or "")
    return (m.group(2), m.group(1)) if m else (None, None)

feeds = {}
for a in pdus:
    idx, side = base(a.get("NAME"))
    if idx:
        feeds.setdefault(idx, set()).add(side)
for idx, sides in sorted(feeds.items()):
    if sides != {"A", "B"}:
        missing = {"A", "B"} - sides
        issues.append(f"[이중화] PDU 그룹 {idx}: {','.join(missing)} 피드 누락 "
                      f"(A/B 이중화 위반)")

# 네트워크 포트 검증
for ins in msp.query("INSERT"):
    if ins.dxf.name != "RACK":
        continue
    attrs = {a.dxf.tag: a.dxf.text for a in ins.attribs}
    ports = int(attrs.get("PORTS", 0) or 0)
    if ports > 48:
        issues.append(f"[네트워크] {attrs.get('ID','?')}: 포트 {ports}개 "
                      f"(단일 랙 권장 48 초과)")

if issues:
    print(f"  ⚠ 검증 위반 {len(issues)}건:")
    for i in issues:
        print(f"    - {i}")
else:
    print("  ✓ 위반 없음")
print()

# ---------- 3) 이미지컷 렌더링 ----------
print("=== 3) 이미지컷 렌더링 ===")
fig = plt.figure(figsize=(10, 8))
ax = fig.add_axes([0, 0, 1, 1])
ctx = RenderContext(doc)
Frontend(ctx, MatplotlibBackend(ax)).draw_layout(msp, finalize=True)
out = "out_imagecut.png"
fig.savefig(out, dpi=150)
print(f"  저장: {out}")
