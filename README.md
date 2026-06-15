# AttoGrid — 데이터센터 DWG 도면 도구

<sub>by **ATTO Research** · 파이썬 패키지명 `attogrid` · **[v1.0.0](https://github.com/annayoon/AttoGrid/releases/tag/v1.0.0)**</sub>

`.dwg` 도면을 **읽고 · 번역하고(중→한) · 전압 등 전기 구성을 검증하고 · 이미지컷으로 추출**하는
데스크톱/웹 앱과 코어 라이브러리입니다.

> **상태:** 실제 데이터센터 도면(AutoCAD 2007, 액침냉각/소방·냉난방 전기 도면, 4.8 MB)으로
> 전 파이프라인 동작 검증 완료. 사내 서버(`10.0.112.254`) 배포 운영 중.

---

## 왜 이렇게 만들었나 — 실파일 검증에서 얻은 결론

오픈소스만으로 DWG를 다루기 위해 두 가지 읽기 경로를 실제 파일로 비교했습니다:

| 경로 | 결과 |
|------|------|
| `dwg2dxf` → DXF 파싱 | ❌ 복잡한 실도면에서 `BLOCK_HEADER` 에러로 DXF가 잘림 |
| **`dwgread -O JSON` → 직접 파싱** | ✅ 115,547개 객체 전부 보존 — **채택** |

추가로 확인된 사실:
- 전압값이 MTEXT 폰트 코드 안에 묻혀 있음(`{\Fxx|c0;220V\F..;电源线}`) → `clean_mtext()`가 정제
- DWG **쓰기(저장)** 는 오픈소스로는 불안정 → 편집 결과는 **DXF/JSON으로 저장** 권장

---

## 기능 현황

| 기능 | 상태 | 비고 |
|------|------|------|
| DWG 읽기 | ✅ | `dwgread` JSON 경로 |
| 텍스트 추출 | ✅ | TEXT/MTEXT + 포맷코드 정제 |
| 번역 대상 분류 | ✅ | 언어(ko/zh/en) 판별, 식별자 자동 제외 |
| **번역 (중→한)** | ✅ | DeepL / argos(오프라인·무료) / Ollama·vLLM(로컬 AI) + 전문용어 사전 |
| **번역 얹기** | ✅ | 한국어 번역을 도면 SVG 위에 오버레이 · "원본으로" 복귀 버튼 |
| 전압/구성 검증 | ✅ | 전압·변압기 용량-부하·전류-차단기·이중화·접지/이중전원·냉방용량(7종) |
| 전압 마커 오버레이 | ✅ | 비표준 전압 위치를 도면 위에 마커로 표시 (격자 중복 제거) |
| 이미지 내보내기 | ✅ | 전체/구획별 PNG·SVG(전압 마커 옵션) |
| 구획 분할 | ✅ | 프레임 자동 감지 / 공간 클러스터 / 격자(NxM) |
| **SVG 고해상도 렌더** | ✅ | viewBox 직접 조작 팬/줌(벡터 재렌더), non-scaling-stroke |
| 2D→3D 모델링 | ✅ | 닫힌 윤곽 압출(three.js), PBR 재질·그림자·OrbitControls |
| 웹 서버 모드 | ✅ | Flask REST API + nginx 프록시, 브라우저 접근 가능 |
| DWG 편집·저장 | ⛔ | DXF/JSON 저장으로 대체 |

---

## 설치

### 로컬 (macOS)

```bash
# 1) libredwg (DWG 읽기) — Homebrew
brew install libredwg

# 2) 파이썬 의존성
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) argos 언어 모델 (오프라인 번역용, 최초 1회)
python -c "
from argostranslate import package as p; p.update_package_index()
[p.install_from_path(x.download()) for x in p.get_available_packages()
 if (x.from_code,x.to_code) in (('zh','en'),('en','ko'))]"
```

### 서버 배포 (Linux)

```bash
# 코드 업로드 + 서비스 설치
bash deploy/server_connect.sh deploy

# 이후 코드만 업데이트할 때
bash deploy/server_connect.sh deploy
ssh root@10.0.112.254 "systemctl restart attogrid"
```

> **포트 5000 충돌 (macOS):** AirPlay Receiver가 5000을 점유합니다.  
> `python web_app.py --port 5001` 로 우회하거나 시스템 설정에서 AirPlay Receiver를 끄세요.

---

## 실행 방법

### 데스크톱 앱 (pywebview)

```bash
python app.py
```

네이티브 창 안에 HTML/JS UI가 뜹니다. 탭 구성:

| 탭 | 설명 |
|----|------|
| 개요 | 객체/레이어 수, 엔티티 분포 |
| 도면 | SVG 렌더 + 팬/줌 · 번역 얹기 · 구획 분할 · 이미지 저장 |
| 텍스트 | 추출 텍스트 + 언어 분류 + 번역 |
| 전압 검증 | 비표준 전압/구성 위반 목록 + 도면 마커 |
| 3D | 닫힌 윤곽 박스 압출(three.js) |
| 번역 | 엔진 선택(argos/DeepL/Ollama/mock) + CSV 내보내기 |

### 웹 서버 모드 (Flask)

```bash
python web_app.py                   # 기본 포트 5000
python web_app.py --port 5001       # 포트 충돌 시
```

브라우저에서 `http://localhost:5000` (또는 지정 포트)으로 접근합니다.  
서버 배포 시 nginx 리버스 프록시(포트 80)와 systemd 서비스로 운영합니다.

### CLI

```bash
python cli.py inspect   도면.dwg                           # 엔티티/레이어 요약
python cli.py texts     도면.dwg --translatable            # 번역 대상 텍스트
python cli.py validate  도면.dwg --rules attogrid/rules/datacenter.json
python cli.py translate 도면.dwg --to ko                   # 중→한 번역
python cli.py svg       도면.dwg out.svg                   # SVG 이미지컷
```

---

## 번역 (중→한)

네 가지 백엔드를 지원합니다:

| 백엔드 | 비용 | 품질 | 비고 |
|--------|------|------|------|
| `glossary` | **무료·즉시** | 용어집 범위 | 네트워크·모델 불필요, 전문용어 일관성 최고 |
| `argos` | **무료·오프라인** | 보통 | 인터넷 불필요, zh→en→ko 피벗, 최초 1회 모델 설치 |
| `ollama` | **무료·로컬** | 높음(모델 의존) | Ollama 또는 vLLM 서버 필요 |
| `deepl` | 무료 50만자/월~ | **높음** | `DEEPL_API_KEY` 필요 |

번역 설계의 핵심은 **전처리/후처리 보호**입니다:

- 식별자·전압값·규격코드 → `<x>…</x>` 태그로 감싸 번역 엔진이 건드리지 않음
- 도메인 용어는 `attogrid/glossary/zh_ko.json` 사전으로 통일
  (예: `七氟丙烷` → `헵타플루오로프로판(FM-200)`, `空调` → `에어컨`, `暖通` → `공조`)
- CJK 문자 없는 구간(숫자·영문 등)은 번역 건너뜀 — argos 모델 오번역 방지
- 동일 텍스트 1회만 번역 → `.attogrid_cache.json`에 캐시

```bash
# glossary (즉시, 엔진 불필요)
python cli.py translate 도면.dwg --backend glossary

# argos (최초 1회 모델 설치 후 오프라인 동작)
python cli.py translate 도면.dwg --backend argos

# Ollama / vLLM (로컬 AI 서버)
# OLLAMA_HOST=http://서버IP:포트 python web_app.py
python web_app.py  # 번역 탭에서 'Ollama' 선택

# DeepL
export DEEPL_API_KEY="...:fx"
python cli.py translate 도면.dwg --backend deepl --out 번역.json
```

---

## 전압/전기 구성 검증

`attogrid/rules/datacenter.json` 기준으로 **7가지**를 검증합니다:

| # | 항목 | 심각도 | 내용 |
|---|------|--------|------|
| 1 | 전압 레벨 | warning | 허용 목록(380V·220V·110V…) 외 전압 감지, 3단계 판단 |
| 2 | 필수 항목 | warning | 接地(접지)·双电源(이중전원) 표기 존재 여부 |
| 3 | 변압기 용량 | warning | `xxxKVA` vs `Pjs=xxxkW` 비교(역률 0.9 적용) |
| 4 | 차단기 정격 | warning | `Ijs=xxxA` vs `In=xxxA` / `xxxA/xP` 비교 |
| 5 | 이중화 구성 | warning | ATS·双电源(절체장치), 발전기·UPS·备用(예비전원) 표기 확인 |
| 6 | 냉방 용량 | info | 制冷量 합계 요약(정보성) |
| 7 | 금지 패턴 | error | `TODO`, `미정`, `???` 미완성 표기 검출 |

규칙은 JSON 파일을 직접 편집해 커스터마이즈할 수 있습니다.

```python
import attogrid
d = attogrid.read("도면.dwg")
findings = attogrid.validate(
    [i.text for i in attogrid.extract_texts(d)],
    attogrid.load_rules("attogrid/rules/datacenter.json")
)
```

---

## SVG 렌더링 품질

고해상도·선명한 도면 표시를 위해 세 가지 기법을 조합합니다:

1. **3000px SVG 출력** — 서버사이드에서 width=3000으로 생성
2. **viewBox 직접 조작 팬/줌** — CSS `transform: scale()` 대신 SVG viewBox 속성을 직접 변경 → 매 줌 레벨에서 벡터 재렌더, 비트맵 뭉개짐 없음
3. **non-scaling-stroke** — `vector-effect: non-scaling-stroke` 로 어떤 줌에서도 1px 선 굵기 유지

---

## 프로젝트 구조

```
attogrid/
  reader.py        DWG/JSON 읽기 (dwgread 경로)
  text.py          텍스트 추출 + MTEXT 정제 + 언어 분류
  translate.py     번역 파이프라인 (보호·사전·캐시·백엔드 추상화)
  translate_ollama.py  Ollama/vLLM 백엔드
  validate.py      전압/구성 검증 규칙 엔진
  render.py        SVG/PNG 렌더 (팬/줌·마커·구획박스·번역 오버레이)
  model3d.py       2D→3D 압출 (푸트프린트 정규화)
  rules/           검증 규칙 JSON (표준별로 수정 가능)
  glossary/        번역 전문용어 사전 (중→한)
app.py             데스크톱 앱 (pywebview) + JS 브리지 Api
web_app.py         Flask 웹 서버 (REST API)
ui/                프론트엔드 HTML/JS/CSS + three.js 벤더
cli.py             커맨드라인 진입점
deploy/
  setup.sh         서버 설치 스크립트 (venv·nginx·systemd)
  server_connect.sh  SSH/배포/재시작 원커맨드 헬퍼
  nginx.conf       nginx 리버스 프록시 설정
  attogrid.service systemd 서비스 유닛
```

---

## 로드맵

- [x] `dwgread` JSON 읽기 경로 채택
- [x] 텍스트 추출 + MTEXT 정제
- [x] 번역 파이프라인 (DeepL / argos / Ollama·vLLM)
- [x] 전압/구성 검증 7종
- [x] SVG 이미지컷 (JSON 지오메트리 직접 렌더, 3000px 고해상도)
- [x] SVG 고해상도 팬/줌 (viewBox 방식)
- [x] pywebview 데스크톱 앱
- [x] Flask 웹 서버 + nginx 배포
- [x] 2D→3D 압출 뷰 (three.js)
- [x] 번역 텍스트 도면 오버레이 (번역 얹기 + 원본 복귀)
- [x] 사내 서버 배포 (10.0.112.254, systemd 상시 운영)
- [ ] 검증 규칙 심화 (케이블 색상 코드, 부하 구역별 분석)
- [ ] 네트워크 토폴로지 추출 → EVE-NG 연동 (조사 완료)

---

## 라이선스

본 프로젝트 코드: **MIT** (ATTO Research) — `LICENSE` 참고.

`libredwg`(GPL-3.0)는 별도 프로세스로 호출만 하고 번들하지 않으므로
본 코드는 MIT로 배포됩니다. 사용자는 libredwg를 직접 설치합니다.

---

## 주의 — 고객 도면 비공개

실제 도면(`*.dwg`, `real.*`, `*.json`)은 `.gitignore`로 저장소에서 제외됩니다.
민감/독점 도면을 커밋하지 마세요.
