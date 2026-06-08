"""
데이터센터 전기/네트워크 도면을 모사한 합성 DXF 생성.
실제 DWG 샘플이 들어오기 전, 파이프라인 검증용 입력을 만든다.
"""
import ezdxf

doc = ezdxf.new("R2010", setup=True)  # 한글 등 유니코드 텍스트 지원 버전
msp = doc.modelspace()

# --- 레이어 구성 (데이터센터 관례) ---
doc.layers.add("E-POWER",   color=1)   # 전력
doc.layers.add("E-NETWORK", color=5)   # 네트워크
doc.layers.add("RACK",      color=7)   # 랙 윤곽
doc.layers.add("TEXT-KO",   color=3)   # 한글 주석(번역 대상)

# --- PDU 블록 정의 (속성: 이름, 전압, 피드 A/B) ---
pdu = doc.blocks.new(name="PDU")
pdu.add_lwpolyline([(0, 0), (2, 0), (2, 3), (0, 3), (0, 0)])
pdu.add_attdef("NAME",    insert=(0.2, 2.4), height=0.3)
pdu.add_attdef("VOLTAGE", insert=(0.2, 1.6), height=0.3)
pdu.add_attdef("FEED",    insert=(0.2, 0.8), height=0.3)

# --- RACK 블록 정의 (속성: 랙 ID, 포트 수) ---
rack = doc.blocks.new(name="RACK")
rack.add_lwpolyline([(0, 0), (1, 0), (1, 2), (0, 2), (0, 0)])
rack.add_attdef("ID",    insert=(0.1, 1.5), height=0.25)
rack.add_attdef("PORTS", insert=(0.1, 0.9), height=0.25)

# --- 전기: PDU 배치 (A/B 이중화 피드) ---
# 정상 전압 레벨: 480V(공급), 208V/120V(분전). 일부러 오류 하나 포함.
pdus = [
    {"pos": (1, 10),  "NAME": "PDU-A1", "VOLTAGE": "480V", "FEED": "A"},
    {"pos": (1, 5),   "NAME": "PDU-B1", "VOLTAGE": "480V", "FEED": "B"},
    {"pos": (6, 10),  "NAME": "PDU-A2", "VOLTAGE": "208V", "FEED": "A"},
    {"pos": (6, 5),   "NAME": "PDU-B2", "VOLTAGE": "210V", "FEED": "B"},  # ← 오류: 210V (비표준)
    {"pos": (11, 10), "NAME": "PDU-A3", "VOLTAGE": "120V", "FEED": "A"},
    # PDU-B3 누락 → A/B 이중화 위반 (A3에 짝 B3 없음)
]
for p in pdus:
    ref = msp.add_blockref("PDU", p["pos"], dxfattribs={"layer": "E-POWER"})
    ref.add_auto_attribs({"NAME": p["NAME"], "VOLTAGE": p["VOLTAGE"], "FEED": p["FEED"]})

# --- 네트워크: 랙 배치 ---
racks = [
    {"pos": (1, 0),  "ID": "R-01", "PORTS": "48"},
    {"pos": (3, 0),  "ID": "R-02", "PORTS": "48"},
    {"pos": (5, 0),  "ID": "R-03", "PORTS": "96"},   # 포트 과다 후보
    {"pos": (7, 0),  "ID": "R-04", "PORTS": "48"},
]
for r in racks:
    ref = msp.add_blockref("RACK", r["pos"], dxfattribs={"layer": "E-NETWORK"})
    ref.add_auto_attribs({"ID": r["ID"], "PORTS": r["PORTS"]})

# --- 한글 주석 (번역 대상 텍스트) ---
msp.add_text("주 배전반 - 480V 3상", height=0.5,
             dxfattribs={"layer": "TEXT-KO", "insert": (1, 14)})
msp.add_text("네트워크 랙 열 (예비 회선 포함)", height=0.5,
             dxfattribs={"layer": "TEXT-KO", "insert": (1, -1.5)})
# 번역 제외 대상(식별자/회로명)도 섞어둠
msp.add_text("CIRCUIT-A-12", height=0.4,
             dxfattribs={"layer": "TEXT-KO", "insert": (8, 14)})

doc.saveas("sample.dxf")
print("생성 완료: sample.dxf")
print(f"  레이어 {len(doc.layers)}개, 모델스페이스 엔티티 {len(msp)}개")
