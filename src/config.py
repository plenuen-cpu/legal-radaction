"""앱 상수와 실행 설정."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "LegalDeid"
APP_TITLE = "법률문서 비식별화"
APP_VERSION = "1.0.0"
APP_SUBTITLE = "PDF → 로컬 OCR · 정규식 · 로컬 LLM → TXT / DOCX"

# 비식별화 표기 방식
STYLE_PSEUDONYM = "pseudonym"   # [이름1], [주소1] ...
STYLE_MASK = "mask"             # ***
STYLES = (STYLE_PSEUDONYM, STYLE_MASK)

DEFAULT_DPI = 300
MIN_PAGE_TEXT_CHARS = 20        # 이보다 적으면 스캔 페이지로 판단


@dataclass(frozen=True)
class ModelSpec:
    key: str
    name: str
    repo: str
    filename: str
    size: int
    sha256: str
    prompt_format: str          # "gemma" | "llama3" | "exaone" | "chatml"
    params_b: float
    languages: str
    license_name: str
    license_url: str
    commercial_ok: bool
    recommended: bool = False

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/main/{self.filename}?download=true"

    @property
    def size_gb(self) -> float:
        return round(self.size / (1024 ** 3), 2)

    @property
    def license_label(self) -> str:
        return "상업용 사용 가능" if self.commercial_ok else "연구/개인용(업무용 불가)"


# 기본값은 한국어 성능이 좋고 가벼운 EXAONE 3.5 2.4B(연구·개인용 라이선스).
# 업무(상업)용으로 쓸 때는 라이선스가 허용하는 Gemma 3 4B / Llama 3.2 3B를 고른다.
# - EXAONE 3.5: EXAONE AI Model License 1.1 - NC (연구·비상업용)
# - Qwen2.5-3B: Qwen Research License (연구용)
# - Gemma 3: Gemma Terms of Use — 상업적 사용 허용(금지 용도 조항 준수)
# - Llama 3.2: Llama 3.2 Community License — 상업적 사용 허용(월 7억 MAU 미만)
MODEL_SPECS: dict[str, ModelSpec] = {
    "gemma-3-4b-it-q4km": ModelSpec(
        key="gemma-3-4b-it-q4km",
        name="Gemma 3 4B Instruct (Q4_K_M)",
        repo="unsloth/gemma-3-4b-it-GGUF",
        filename="gemma-3-4b-it-Q4_K_M.gguf",
        size=2_489_894_016,
        sha256="04a43a22e8d2003deda5acc262f68ec1005fa76c735a9962a8c77042a74a7d19",
        prompt_format="gemma",
        params_b=4.0,
        languages="한국어·영어 외 다국어",
        license_name="Gemma Terms of Use",
        license_url="https://ai.google.dev/gemma/terms",
        commercial_ok=True,
        recommended=True,
    ),
    "llama-3.2-3b-instruct-q4km": ModelSpec(
        key="llama-3.2-3b-instruct-q4km",
        name="Llama 3.2 3B Instruct (Q4_K_M)",
        repo="bartowski/Llama-3.2-3B-Instruct-GGUF",
        filename="Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        size=2_019_377_696,
        sha256="6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff",
        prompt_format="llama3",
        params_b=3.0,
        languages="한국어·영어 외 다국어",
        license_name="Llama 3.2 Community License",
        license_url="https://www.llama.com/llama3_2/license/",
        commercial_ok=True,
    ),
    "exaone-3.5-2.4b-q4km": ModelSpec(
        key="exaone-3.5-2.4b-q4km",
        name="EXAONE 3.5 2.4B Instruct (Q4_K_M)",
        repo="LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct-GGUF",
        filename="EXAONE-3.5-2.4B-Instruct-Q4_K_M.gguf",
        size=1_644_918_272,
        sha256="1660a3794acc33437137faab5cb3fb2b2c4191d0a4ec991d4c31a7197cb2cdbf",
        prompt_format="exaone",
        params_b=2.4,
        languages="한국어·영어",
        license_name="EXAONE AI Model License 1.1 - NC",
        license_url="https://huggingface.co/LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct-GGUF",
        commercial_ok=False,
        recommended=True,
    ),
    "qwen2.5-3b-instruct-q4km": ModelSpec(
        key="qwen2.5-3b-instruct-q4km",
        name="Qwen2.5 3B Instruct (Q4_K_M)",
        repo="Qwen/Qwen2.5-3B-Instruct-GGUF",
        filename="qwen2.5-3b-instruct-q4_k_m.gguf",
        size=2_104_932_768,
        sha256="626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d",
        prompt_format="chatml",
        params_b=3.0,
        languages="한국어·영어",
        license_name="Qwen Research License",
        license_url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF",
        commercial_ok=False,
    ),
}

DEFAULT_MODEL_KEY = "exaone-3.5-2.4b-q4km"

LLM_SYSTEM_PROMPT = (
    "당신은 한국어 법률문서에서 개인정보를 찾아내는 전문가입니다. "
    "문서 조각에서 실명(사람 이름), 상세 주소, 회사·민간기관 이름만 정확히 찾아 JSON 배열로만 출력합니다."
)

LLM_USER_TEMPLATE = """아래 문서 조각에서 비식별화 대상만 추출하세요.

규칙:
1. 문서 조각에 실제로 들어 있는 문자열만 그대로 적습니다. 요약하거나 바꾸지 않습니다.
2. 유형은 PERSON(사람 이름), ADDRESS(상세 주소), ORG(회사·법인·민간단체 이름) 중 하나입니다.
3. 다음은 절대 넣지 않습니다: 법원명(대법원, 서울중앙지방법원 등), 재판부(제3민사부 등), 판사·검사·변호사 직위, 법령명(민법, 제750조 등), 판례·사건번호(2020다12345, 2020가합12345 등), 날짜, 금액, 이미 [이름1]처럼 치환된 표시, 일반 명사.
4. 주소는 도로명·지번과 건물명·동·층·호수를 포함해 추출합니다. 예: "서울특별시 강남구 테헤란로 123 4층 402호"
5. 확실하지 않으면 넣지 않습니다. 없으면 [] 만 출력합니다.
6. 설명, 사과, 코드블록 없이 JSON 배열만 출력합니다.

출력 예:
[{{"type": "PERSON", "text": "김민수"}}, {{"type": "ADDRESS", "text": "서울특별시 강남구 테헤란로 123 4층"}}, {{"type": "ORG", "text": "주식회사 한빛테크"}}]

문서 조각:
\"\"\"
{chunk}
\"\"\"
"""


@dataclass
class PipelineConfig:
    """한 문서 처리에 쓰이는 설정 묶음."""

    style: str = STYLE_PSEUDONYM
    mask_text: str = "***"
    use_llm: bool = True
    model_key: str | None = DEFAULT_MODEL_KEY
    model_path: str | None = None
    dpi: int = DEFAULT_DPI
    force_ocr: bool = False
    save_mapping: bool = True
    chunk_size: int = 1200
    max_llm_tokens: int = 512
    n_threads: int | None = None
    n_ctx: int = 2048
    add_docx_notice: bool = False
    keep_page_breaks: bool = True

    def resolved_model_key(self) -> str:
        return self.model_key or DEFAULT_MODEL_KEY


@dataclass
class Settings:
    """GUI 재실행 시 기억하는 값(개인정보 없음)."""

    output_dir: str = ""
    style: str = STYLE_PSEUDONYM
    use_llm: bool = True
    save_mapping: bool = True
    dpi: int = DEFAULT_DPI
    model_key: str = DEFAULT_MODEL_KEY
    last_input_dir: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        base = cls()
        for key, value in (data or {}).items():
            if hasattr(base, key) and isinstance(value, type(getattr(base, key))):
                setattr(base, key, value)
        return base


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def default_output_dir(source_pdf: Path) -> Path:
    return Path(source_pdf).resolve().parent
