# 🛡️ LegalDeid — 법률문서 로컬 AI 비식별화

한국어 법률문서(PDF)를 **인터넷에 올리지 않고** 내 컴퓨터에서만 처리해 개인정보를 가린 뒤
`.txt`와 `.docx`(워드)로 저장하는 윈도우용 단독 실행 프로그램입니다.

- 대상 문서: 판결문, 소장, 준비서면, 계약서, 진술조서 등 한국어 PDF
- 처리 방식: **텍스트 PDF는 그대로 추출**, 스캔 PDF만 고해상도 OCR(한국어)
- 1차 **정규식**으로 주민등록번호·전화·계좌·카드·주소 등을 결정적으로 치환
- 2차 **로컬 LLM**(GGUF, CPU)으로 문맥 속 사람 이름·상세 주소·회사/기관명을 찾아 치환
- 결과: `원본_비식별화.txt`, `원본_비식별화.docx`, (선택) `원본_비식별화_대조표.csv`
- 표기: `[이름1] [주소1] [회사1] …` 가명화(기본) 또는 `***` 마스킹

> ⚠️ 자동 처리 결과는 100% 완벽하지 않습니다. **대조표를 원문과 함께 검수**한 뒤 사용하세요.

## 내려받기

- 최신 릴리스: <https://github.com/plenuen-cpu/legal-radaction/releases/latest>
- `LegalDeid-windows.zip` (약 206MB) — Windows 10/11 64bit, 설치 불필요
- 빌드: GitHub Actions `windows-latest` / Python 3.11 / PyInstaller — 테스트 80개 통과 후 자동 패키징

---

## 1. 빠른 시작 (일반 사용자)

1. `LegalDeid-windows.zip` 압축을 풉니다(폴더째로 두고 쓰는 포터블 방식, 설치 불필요).
2. `LegalDeid.exe`를 실행합니다.
3. **PDF 파일 선택** → 비식별화 방식 선택 → **비식별화 시작**.
4. 처음 한 번은 **모델 다운로드**(기본 EXAONE 2.4B, 1.6GB)를 누릅니다.
   이미 `models` 폴더에 `.gguf` 파일이 있으면 그대로 인식합니다(완전 오프라인).
5. 완료 후 **결과 폴더 열기**를 누르면 TXT·DOCX·대조표가 있습니다.

### 화면 구성

| 영역 | 설명 |
| --- | --- |
| 1. PDF 파일 | 여러 개 선택 가능, 끌어다 놓기 지원(tkinterdnd2 포함 시) |
| 2. 비식별화 방식 | `가명화 [이름1]` / `마스킹 ***` |
| 옵션 | AI 문맥 분석 사용, 치환 대조표 저장, 스캔 PDF 강제 OCR |
| 로컬 AI 모델 | 모델 선택·다운로드, 라이선스 표시 |
| 3. 저장 폴더 | 비우면 원본 PDF와 같은 폴더 |
| 진행/로그 | OCR → AI 분석 → 저장 단계와 결과 경로 표시 |

---

## 2. 어떤 개인정보를 가리나요

**정규식(1차, 결정적)**

| 유형 | 예 | 표기 |
| --- | --- | --- |
| 주민등록·외국인등록번호 | `900101-1234568` | `[주민번호1]` |
| 법인등록번호 | `110111-1234568` | `[법인번호1]` |
| 사업자등록번호 | `123-45-67891` | `[사업자번호1]` |
| 휴대전화·일반전화 | `010-1234-5678`, `02-345-6789` | `[전화1]` |
| 이메일 | `a@b.co.kr` | `[이메일1]` |
| 계좌번호 | `계좌번호: 110-123-456789` | `[계좌1]` |
| 카드번호 | `1234-5678-9012-3452` | `[카드1]` |
| 차량번호 | `12가3456` | `[차량1]` |
| 여권·운전면허 | `M12345678`, `12-34-567890-12` | `[여권1]` `[면허1]` |
| 상세 주소 | `서울특별시 강남구 테헤란로 123, 4층 402호` | `[주소1]` |
| 생년월일(라벨 있을 때) | `생년월일: 1990. 1. 1.` | `[생년월일1]` |

**로컬 LLM(2차, 문맥)**

- 당사자·증인·참고인·대표이사 등의 **실명**
- 도로명·지번·건물·동·호수까지 포함한 **상세 주소**
- **회사·법인·민간기관 이름** (`주식회사 ○○`, `㈜○○`, `재단법인 ○○` 등)

**가리지 않는 것(중요)**

- 법원명·재판부: `대법원`, `서울중앙지방법원`, `제3민사부`
- 법령: `민법 제750조`, `상법 제65조`
- 판례·사건번호: `대법원 2020다12345`, `2020가합12345`
- 검찰청·경찰서·행정기관 등 공공기관
- 날짜·금액·일반 명사

---

## 3. 처리 흐름

```
PDF
 ├─ PyMuPDF로 페이지별 텍스트 확인
 │    ├─ 텍스트 PDF  → 그대로 추출(빠름)
 │    └─ 스캔 PDF    → 300 DPI 렌더링 → RapidOCR(ONNX) 한국어 모델
 ├─ 1차 정규식 치환 (주민번호·전화·계좌·카드·주소 …)
 ├─ 2차 로컬 LLM 문맥 분석 (이름·주소·회사) + 가드(법원·법령·판례 제외)
 └─ TXT / DOCX / 대조표 저장
```

- 같은 사람·회사는 문서 전체에서 **같은 번호**로 매핑됩니다([이름1] …).
- 한 번 역할 표지(`원고 김민수`)로 확인된 이름은 문서의 다른 등장 위치도 함께 치환합니다.
- 이름 뒤 조사(`은/는/이/가`)는 원문 그대로 둡니다(`[이름1]은`).

---

## 4. 로컬 AI 모델

| 모델 | 크기 | 라이선스 | 용도 | 특징 |
| --- | --- | --- | --- | --- |
| **EXAONE 3.5 2.4B Instruct** (기본) | 1.64GB | EXAONE AI Model License 1.1 – **NC**(연구·비상업) | 개인·연구용 | 한국어 강점, 가장 가볍고 빠름 |
| Gemma 3 4B Instruct | 2.49GB | Gemma Terms of Use | **상업용 사용 가능** | 한국어 우수, CPU에서 다소 무거움 |
| Llama 3.2 3B Instruct | 2.02GB | Llama 3.2 Community License | **상업용 사용 가능** | 경량·빠름, 한국어 보통 |
| Qwen2.5 3B Instruct | 2.10GB | Qwen Research License | 연구용 | 다국어 |

- 기본값은 EXAONE 3.5 2.4B입니다(개인·연구 용도).
- **회사 업무(상업적) 목적으로 쓸 때는 Gemma 3 4B 또는 Llama 3.2 3B를 선택**하세요.
  EXAONE/Qwen은 비상업 라이선스라 업무용 사용이 허용되지 않습니다.
- 모델 파일은 Hugging Face에서 SHA-256 검증 후 내려받습니다. 파일을 직접 `models/`에 넣어도 됩니다.

### 완전 오프라인으로 쓰기

```
LegalDeid/
├─ LegalDeid.exe
├─ models/
│  ├─ EXAONE-3.5-2.4B-Instruct-Q4_K_M.gguf
│  └─ ocr/ (프로그램에 포함)
```

`models/` 폴더에 `.gguf` 파일을 넣으면 인터넷 없이 실행됩니다.
(파일명이 달라도 `models/`의 첫 GGUF를 사용합니다.)

### 요구 사양

| 항목 | 최소 | 권장 |
| --- | --- | --- |
| OS | Windows 10 64bit | Windows 11 64bit |
| 메모리 | 4GB(정규식만) / 8GB(AI) | 16GB |
| 디스크 | 1GB(프로그램) + 1.6~2.5GB(모델) | 5GB 여유 |
| GPU | 불필요(CPU 전용) | — |

- 스캔 1쪽 OCR: 약 4~7초, AI 문맥 분석: 1,200자 구간당 약 10~40초(CPU 성능에 따라).
- 텍스트 PDF는 OCR을 건너뛰므로 훨씬 빠릅니다.

---

## 5. 개인정보·보안

- **완전 로컬 처리**: 문서 내용은 외부로 전송되지 않습니다. 네트워크는 모델 최초 다운로드에만 사용됩니다.
- 설정·로그는 `%LOCALAPPDATA%\LegalDeid\`에 저장되며 문서 내용은 남기지 않습니다.
- 결과 파일은 원본과 같은 폴더(또는 지정 폴더)에 저장되고, 같은 이름이 있으면 `(2)`를 붙여 덮어쓰지 않습니다.
- 대조표(CSV)에는 **원문 개인정보가 그대로 들어 있으므로** 배포·보관에 주의하세요.

---

## 6. 개발자용

### 설치

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-llm.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python tools/fetch_ocr_models.py     # models/ocr/*.onnx (약 19MB)
```

### 실행

```bash
python main.py                       # GUI
python src/cli.py 문서.pdf -o 결과   # CLI
python src/cli.py *.pdf --style mask --no-llm
python src/download_model.py --model exaone-3.5-2.4b-q4km
```

### 테스트

```bash
pytest -q -m "not slow"     # 단위 테스트(약 7초)
pytest -q -m slow           # OCR 실제 인식 테스트(수 초)
pytest -q                   # 전체
```

테스트는 샘플 한국어 판결문 PDF(텍스트/스캔)를 즉석에서 만들어
정규식·치환 일관성·LLM 가드·DOCX/TXT/CSV 출력·OCR 연동을 검증합니다.

### 윈도우 빌드

```powershell
pip install -r requirements-windows.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python tools/fetch_ocr_models.py
pyinstaller build_windows.spec --noconfirm --clean
# 결과: dist/LegalDeid/LegalDeid.exe (+ models/ocr, DLL)
```

### GitHub Actions

`.github/workflows/build-windows.yml`(원본 `ci/build-windows.yml`)이
`windows-latest`에서 의존성 설치 → 테스트 → PyInstaller 빌드 → `LegalDeid-windows.zip` 업로드 →
태그(`v*`) 푸시 시 GitHub Release 첨부까지 수행합니다.

### 폴더 구조

```
legal-deid/
├─ main.py                     # 진입점(GUI)
├─ build_windows.spec          # PyInstaller(onedir) 설정
├─ ci/build-windows.yml        # GitHub Actions 원본
├─ .github/workflows/          # 실제 실행되는 워크플로
├─ src/
│  ├─ app.py                   # CustomTkinter GUI
│  ├─ cli.py                   # 명령줄 실행기
│  ├─ download_model.py        # 모델 다운로드 도우미
│  ├─ pipeline.py              # OCR→비식별화→저장 오케스트레이터
│  ├─ ocr_pipeline.py          # PyMuPDF + RapidOCR(한국어)
│  ├─ patterns.py              # 정규식 규칙·검증기·제외 가드
│  ├─ deidentifier.py          # 치환 엔진·매핑 테이블·LLM 가드
│  ├─ llm_engine.py            # llama-cpp-python 래퍼(Gemma/Llama/EXAONE/Qwen)
│  ├─ model_manager.py         # GGUF 다운로드·SHA-256 검증·이어받기
│  ├─ exporter.py              # TXT / DOCX / 대조표 CSV
│  ├─ config.py, paths.py
├─ tests/                      # pytest (샘플 PDF 자동 생성)
├─ tools/fetch_ocr_models.py   # OCR 모델 내려받기(빌드 전)
├─ models/ocr/                 # OCR ONNX 모델(배포 포함)
└─ docs/사용법.txt             # 배포 zip에 들어가는 안내문
```

---

### 실행 진단

```powershell
LegalDeid.exe --selftest
# 로그: %LOCALAPPDATA%\LegalDeid\logs\selftest.log
```

Tk·OCR 모델·llama-cpp 등 구성요소와 GUI 창 생성까지 점검합니다.

---

## 7. 한계와 주의

- OCR은 스캔 품질·기울기·도장에 따라 오탈자가 생길 수 있습니다. 숫자 한 글자가 틀리면 정규식이 놓칠 수 있습니다.
- 2.4~4B급 소형 LLM은 긴 문서에서 이름을 일부 놓치거나 회사명을 놓칠 수 있습니다.
  중요한 문서는 **AI 문맥 분석 사용 + 대조표 검수**를 권합니다.
- 법인등록번호와 주민등록번호는 형식이 같아, 생년월일이 성립하지 않는 번호는 법인번호로 분류합니다.
- 이 프로그램은 **비식별화 보조 도구**이며 법적 판단을 대신하지 않습니다. 원본은 반드시 보관하세요.

## 8. 라이선스

- 이 프로그램의 소스: 사용자 내부용.
- 포함된 오픈소스: PyMuPDF, RapidOCR(ONNX), python-docx, CustomTkinter, llama-cpp-python 등 각 라이선스를 따릅니다.
- AI 모델은 프로그램과 별도 라이선스입니다(위 표 참조). 특히 **EXAONE 3.5/Qwen2.5는 비상업(연구)용**입니다.
