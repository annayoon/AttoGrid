# AttoGrid — 데이터센터 DWG 도면 도구

<sub>by **ATTO Research** · 파이썬 패키지명 `attogrid`</sub>

`.dwg` 도면을 **읽고 · 번역하고(중/한) · 전압 등 전기 구성을 검증하고 · 이미지컷으로 추출**하는
오픈소스 데스크톱 앱의 코어 라이브러리입니다. (3D 모델링은 로드맵 단계)

> **상태:** 코어 파이프라인 검증 완료(PoC). 실제 4.8MB 데이터센터 도면(AutoCAD 2007,
> 액침냉각/소방 전기 도면)으로 동작을 확인했습니다.

## 왜 이렇게 만들었나 — 실파일 검증에서 얻은 결론

오픈소스만으로 DWG를 다루기 위해 두 가지 읽기 경로를 실제 파일로 비교했습니다:

| 경로 | 결과 |
|------|------|
| `dwg2dxf` → DXF 파싱 | ❌ 복잡한 실도면에서 `BLOCK_HEADER` 에러로 DXF가 잘림 |
| **`dwgread -O JSON` → 직접 파싱** | ✅ 115,547개 객체 전부 보존 — **채택** |

그래서 이 라이브러리의 기본 읽기 경로는 **`dwgread`의 JSON 덤프**입니다.

추가로 확인된 사실:
- 전압값이 MTEXT 폰트 코드 안에 묻혀 있음(`{\Fxx|c0;220V\F..;电源线}`) → `clean_mtext()`가 정제
- DWG **쓰기(저장)** 는 오픈소스로는 불안정 → 편집 결과는 **DXF/JSON으로 저장** 권장
- 이미지컷(`dwg2SVG`)은 복잡한 도면에서 **부분 렌더** → 향후 보강 대상

## 기능 현황

| 기능 | 상태 | 비고 |
|------|------|------|
| DWG 읽기 | ✅ | `dwgread` JSON 경로 |
| 텍스트 추출 | ✅ | TEXT/MTEXT + 포맷코드 정제 |
| 번역 대상 분류 | ✅ | 언어(ko/zh/en) 판별, 식별자 자동 제외 |
| **번역 (중→한)** | ✅ | DeepL / argos(오프라인·무료) 백엔드 + 전문용어 사전 + 수치/식별자 보호 |
| 전압/구성 검증 | ✅ | 전압(사유)·변압기 용량-부하·전류-차단기·이중화(절체+예비)·필수항목(접지/이중전원)·냉방용량(정보) |
| 이미지 내보내기 | ✅ | 전체 PNG/SVG(전압 마커 옵션) + 구획 분할(프레임/클러스터/격자)별 저장 |
| DWG 편집·저장 | ⛔ | DXF/JSON 저장으로 대체 |
| 2D→3D 모델링 | ✅ | 닫힌 윤곽 압출(three.js), 앱 3D 탭 |

## 설치

```bash
# 1) libredwg (DWG 읽기/SVG) — Homebrew
brew install libredwg

# 2) 파이썬 의존성
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 데스크톱 앱 실행

```bash
python app.py
```

`attogrid` 코어를 그대로 쓰는 pywebview 기반 네이티브 앱입니다. 탭 구성:

- **개요** — 객체/레이어 수, 엔티티 분포
- **도면** — JSON 지오메트리 직접 SVG 렌더(모델 공간 전체)
- **텍스트** — 추출 텍스트 + 언어 분류(번역 대상 필터)
- **전압 검증** — 비표준 전압/구성 위반 목록
- **3D** — 닫힌 윤곽을 박스로 압출(three.js), 드래그 회전·휠 줌
- **번역** — 엔진(argos/DeepL/mock) 선택해 중→한 번역

UI 소스는 `ui/`(HTML/JS/CSS), JS↔Python 브리지는 `app.py`의 `Api` 클래스입니다.

## 사용법 (CLI)

```bash
python cli.py inspect  도면.dwg            # 엔티티/레이어 요약
python cli.py texts    도면.dwg --translatable   # 번역 대상 텍스트
python cli.py validate 도면.dwg --rules attogrid/rules/datacenter.json
python cli.py translate 도면.dwg --to ko   # 중→한 번역 (DeepL)
python cli.py svg      도면.dwg out.svg     # 이미지컷(부분)
```

`.dwg` 외에 `dwgread`로 미리 덤프한 `.json`도 입력으로 받습니다(대용량 파일 캐시용).

### 번역 (중→한)

두 가지 백엔드를 지원합니다 (`--backend`):

| 백엔드 | 비용 | 품질 | 비고 |
|--------|------|------|------|
| `deepl` | 무료 50만자/월~ | **높음** | `DEEPL_API_KEY` 필요 |
| `argos` | **무료·오프라인** | 보통(노이즈 있음) | 키·인터넷 불필요(모델 설치 후), 영어 경유 |
| `mock` | — | — | 보호/사전 로직만 검증 |

```bash
# DeepL (운영 품질)
export DEEPL_API_KEY="...:fx"
python cli.py translate 도면.dwg --backend deepl --out 번역.json

# argos (무료·오프라인) — 최초 1회 모델 설치 필요
python -c "from argostranslate import package as p; p.update_package_index(); \
  [p.install_from_path(x.download()) for x in p.get_available_packages() \
   if (x.from_code,x.to_code) in (('zh','en'),('en','ko'))]"
python cli.py translate 도면.dwg --backend argos --out 번역.json
```

> **품질 참고:** 어느 백엔드든 전문용어는 glossary가 교정하고 수치/식별자는 보호되지만,
> 연결 문장 품질은 DeepL이 확연히 낫습니다. argos는 무료·오프라인 "미리보기"용으로 적합합니다.

번역 설계의 핵심은 **번역 전후 보호 처리**입니다:

- 식별자(`CIRCUIT-A-12`)·전압값(`380V`, `3200A`)·규격코드(`GB50370-2005`)는
  `<x>…</x>` ignore 태그로 감싸 **DeepL이 건드리지 않습니다.**
- 도메인 용어는 사전(`attogrid/glossary/zh_ko.json`)으로 **한국어 번역을 강제 통일**합니다
  (예: `七氟丙烷` → `헵타플루오로프로판(FM-200)`).
- 동일 텍스트는 1회만 번역하고(`.attogrid_cache.json`에 캐시) 비용을 줄입니다.

키 없이 보호/사전 로직만 확인하려면 `--mock`:

```bash
python cli.py translate 도면.dwg --mock --limit 20
```

## 라이브러리로 사용

```python
import attogrid
d = attogrid.read("도면.dwg")
items = attogrid.extract_texts(d)
findings = attogrid.validate([i.text for i in items], attogrid.load_rules("attogrid/rules/datacenter.json"))
```

## 프로젝트 구조

```
attogrid/            # 코어 라이브러리
  reader.py       #   DWG/JSON 읽기 (dwgread 경로)
  text.py         #   텍스트 추출 + MTEXT 정제 + 언어 분류
  validate.py     #   전압/구성 검증 규칙 엔진
  render.py       #   이미지컷(SVG)
  rules/          #   검증 규칙(JSON, 도면 표준별로 수정)
  glossary/       #   번역 전문용어 사전(중→한)
  model3d.py      #   2D→3D 압출(푸트프린트 정규화)
app.py            # 데스크톱 앱(pywebview) + JS 브리지 Api
ui/               # 앱 프론트엔드 (HTML/JS/CSS, three.js 벤더 포함)
cli.py            # 커맨드라인 진입점
examples/         # 합성 샘플 생성기(공개 가능 데이터)
tests/            # 단위 테스트
```

## 로드맵

1. **번역 연동** — 추출 텍스트 → 번역 API(중→한) → 결과 매핑/재삽입
2. **검증 규칙 심화** — 이중전원(A/B), 부하 합계, ATS/변압기 용량 정합성
3. ~~**이미지컷 보강**~~ — ✅ JSON 지오메트리 직접 SVG 렌더 구현됨
4. ~~**데스크톱 앱**~~ — ✅ pywebview 앱(`app.py`) 구현됨
5. ~~**2D→3D**~~ — ✅ 닫힌 윤곽 압출 뷰(three.js) 구현됨. 랙 전용 추출은 레이어/블록 필터로 확장 가능

## 라이선스

본 프로젝트 코드: **MIT** (ATTO Research) — `LICENSE` 참고.

`libredwg`(GPL-3.0)는 별도 프로세스로 호출만 하고 번들하지 않으므로 본 코드는
MIT로 배포됩니다. 사용자는 libredwg를 직접 설치(`brew install libredwg`)합니다.

## 주의 — 고객 도면 비공개

실제 도면(`*.dwg`, `real.*`, `*.json`)은 `.gitignore`로 저장소에서 제외됩니다.
민감/독점 도면을 커밋하지 마세요.
