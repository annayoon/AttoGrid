# dcdwg — 데이터센터 DWG 도면 도구

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
| 번역 대상 분류 | ✅ | 언어(ko/zh/en) 판별, 식별자 자동 제외 (번역 API 연동은 다음 단계) |
| 전압/구성 검증 | ✅ | 규칙 엔진(`dcdwg/rules/*.json`) |
| 이미지컷 | ⚠️ | `dwg2SVG` 부분 렌더, 보강 예정 |
| DWG 편집·저장 | ⛔ | DXF/JSON 저장으로 대체 |
| 2D→3D 모델링 | ⛔ | 로드맵 |

## 설치

```bash
# 1) libredwg (DWG 읽기/SVG) — Homebrew
brew install libredwg

# 2) 파이썬 의존성
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 사용법 (CLI)

```bash
python cli.py inspect  도면.dwg            # 엔티티/레이어 요약
python cli.py texts    도면.dwg --translatable   # 번역 대상 텍스트
python cli.py validate 도면.dwg --rules dcdwg/rules/datacenter.json
python cli.py svg      도면.dwg out.svg     # 이미지컷(부분)
```

`.dwg` 외에 `dwgread`로 미리 덤프한 `.json`도 입력으로 받습니다(대용량 파일 캐시용).

## 라이브러리로 사용

```python
import dcdwg
d = dcdwg.read("도면.dwg")
items = dcdwg.extract_texts(d)
findings = dcdwg.validate([i.text for i in items], dcdwg.load_rules("dcdwg/rules/datacenter.json"))
```

## 프로젝트 구조

```
dcdwg/            # 코어 라이브러리
  reader.py       #   DWG/JSON 읽기 (dwgread 경로)
  text.py         #   텍스트 추출 + MTEXT 정제 + 언어 분류
  validate.py     #   전압/구성 검증 규칙 엔진
  render.py       #   이미지컷(SVG)
  rules/          #   검증 규칙(JSON, 도면 표준별로 수정)
cli.py            # 커맨드라인 진입점
examples/         # 합성 샘플 생성기(공개 가능 데이터)
tests/            # 단위 테스트
```

## 로드맵

1. **번역 연동** — 추출 텍스트 → 번역 API(중→한) → 결과 매핑/재삽입
2. **검증 규칙 심화** — 이중전원(A/B), 부하 합계, ATS/변압기 용량 정합성
3. **이미지컷 보강** — JSON 지오메트리 직접 렌더 또는 외부 렌더러
4. **데스크톱 앱** — Electron/Tauri UI + 본 코어를 사이드카로
5. **2D→3D** — 랙/장비 배치 압출 뷰

## 라이선스

`libredwg`는 **GPLv3**입니다. 이를 실행 파일로 호출(별도 프로세스)하는 구조이므로
본 코어 코드의 라이선스는 별도 선택 가능하나, 배포 형태에 따라 GPL 영향 범위를
검토하세요. 라이선스 파일은 `LICENSE`에서 지정합니다(현재 미정).

## 주의 — 고객 도면 비공개

실제 도면(`*.dwg`, `real.*`, `*.json`)은 `.gitignore`로 저장소에서 제외됩니다.
민감/독점 도면을 커밋하지 마세요.
