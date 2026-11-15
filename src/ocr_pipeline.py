"""PDF 텍스트 추출 + 한국어 OCR 파이프라인.

- 텍스트가 들어 있는 PDF: PyMuPDF로 바로 추출(빠름, 원문 그대로).
- 스캔 이미지 PDF: 페이지만 고해상도(기본 300 DPI)로 렌더링해 RapidOCR(ONNX) 한국어 모델로 인식.
- 모델은 exe 옆 `models/ocr/`에 함께 배포되어 완전 오프라인으로 동작한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

try:  # PyMuPDF (fitz는 예전 이름)
    import pymupdf as fitz  # type: ignore
except Exception:  # pragma: no cover
    try:
        import fitz  # type: ignore
    except Exception:
        fitz = None

MIN_PAGE_TEXT_CHARS = 20
OCR_MODEL_FILES = {
    "det": "ch_PP-OCRv5_det_mobile.onnx",
    "cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    "rec": "korean_PP-OCRv5_rec_mobile.onnx",
}


class OcrUnavailable(RuntimeError):
    """OCR 엔진 또는 모델을 사용할 수 없을 때."""


def _progress(callback, message: str, current: int = 0, total: int = 0) -> None:
    if callback:
        try:
            callback(message, current, total)
        except TypeError:
            try:
                callback(message)  # 단일 인자 콜백도 허용
            except TypeError:
                pass


@dataclass
class PageText:
    number: int
    text: str
    used_ocr: bool = False

    @property
    def chars(self) -> int:
        return len(self.text.strip())


@dataclass
class OcrConfig:
    dpi: int = 300
    force_ocr: bool = False
    min_text_chars: int = MIN_PAGE_TEXT_CHARS
    max_side_len: int = 3200
    det_limit_side: int = 960


class OcrEngine:
    """RapidOCR(ONNX) 한국어 인식기 래퍼. 첫 호출 때 모델을 로드한다."""

    def __init__(self, models_dir: Optional[Path] = None, config: Optional[OcrConfig] = None):
        self.models_dir = Path(models_dir) if models_dir else None
        self.config = config or OcrConfig()
        self._engine = None

    def _model_paths(self) -> dict:
        if not self.models_dir:
            return {}
        found = {}
        # 배포 시 파일명이 조금 달라도 찾을 수 있게 접두사로 탐색
        for key, filename in OCR_MODEL_FILES.items():
            candidate = self.models_dir / filename
            if candidate.exists():
                found[key] = str(candidate)
                continue
            matches = sorted(self.models_dir.glob(f"*{key}*.onnx"))
            if matches:
                found[key] = str(matches[0])
        return found

    def load(self):
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr import RapidOCR, LangDet, LangRec, ModelType, OCRVersion
        except Exception as exc:  # pragma: no cover
            raise OcrUnavailable(
                "OCR 구성요소(rapidocr)를 불러오지 못했습니다. 설치가 손상되었을 수 있습니다."
            ) from exc

        params = {
            "Global.log_level": "warning",
            "Global.max_side_len": self.config.max_side_len,
            "Global.min_side_len": 30,
            "Det.lang_type": LangDet.CH,
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Det.model_type": ModelType.MOBILE,
            "Det.limit_side_len": self.config.det_limit_side,
            "Det.limit_type": "min",
            "Det.use_cuda": False,
            "Rec.lang_type": LangRec.KOREAN,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.use_cuda": False,
            "Rec.rec_batch_num": 8,
        }
        paths = self._model_paths()
        if "det" in paths:
            params["Det.model_path"] = paths["det"]
        if "rec" in paths:
            params["Rec.model_path"] = paths["rec"]
        if "cls" in paths:
            params["Cls.model_path"] = paths["cls"]

        try:
            self._engine = RapidOCR(params=params)
        except Exception as exc:  # pragma: no cover
            raise OcrUnavailable(f"OCR 모델을 초기화하지 못했습니다: {exc}") from exc
        return self._engine

    def recognize(self, image) -> List[str]:
        engine = self.load()
        result = engine(image)
        texts = getattr(result, "txts", None)
        if texts is None:
            return []
        return [t for t in texts if t and t.strip()]

    def unload(self) -> None:
        """ONNX 세션을 내려 메모리를 돌려준다."""
        self._engine = None

    def recognize_page(self, page) -> str:
        if fitz is None:
            raise OcrUnavailable("PyMuPDF를 불러오지 못했습니다.")
        zoom = self.config.dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
        import numpy as np

        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            image = image[:, :, :3]
        elif pix.n == 1:
            image = np.repeat(image[:, :, None], 3, axis=2)
        lines = self.recognize(image)
        return join_ocr_lines(lines)


def _normalize_text(text: str) -> str:
    """PDF에서 흔한 비분리 공백·전각 공백을 일반 공백으로 바꾼다."""
    return (
        text.replace("\u00a0", " ")
        .replace("\u3000", " ")
        .replace("\ufeff", "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def join_ocr_lines(lines: List[str]) -> str:
    """OCR 줄들을 문서 형태로 합친다. 빈 줄/머리표는 정리."""
    cleaned: List[str] = []
    for raw in lines:
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _page_text_native(page) -> str:
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return page.get_text("text") or ""
    items = []
    for block in blocks:
        if len(block) < 5:
            continue
        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        if text and text.strip():
            items.append((round(y0, 1), round(x0, 1), text.strip()))
    items.sort(key=lambda item: (item[0], item[1]))
    return _normalize_text("\n".join(text for _, _, text in items))


def _image_coverage(page) -> float:
    try:
        page_area = abs(page.rect.width * page.rect.height)
        if page_area <= 0:
            return 0.0
        covered = 0.0
        for image in page.get_images(full=True):
            for rect in page.get_image_rects(image[0]):
                covered += abs(rect.width * rect.height)
        return min(covered / page_area, 1.0)
    except Exception:
        return 0.0


def page_needs_ocr(page, text: str, min_chars: int = MIN_PAGE_TEXT_CHARS) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < min_chars:
        return True
    if _image_coverage(page) > 0.6 and len(stripped) < 200:
        return True
    return False


def extract_pages(
    pdf_path: str | Path,
    config: Optional[OcrConfig] = None,
    progress: Optional[Callable[[str, int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    ocr_engine: Optional[OcrEngine] = None,
    models_dir: Optional[Path] = None,
) -> List[PageText]:
    """PDF에서 페이지별 텍스트를 얻는다(필요한 페이지만 OCR)."""
    if fitz is None:
        raise OcrUnavailable(
            "PyMuPDF(fitz)를 불러오지 못했습니다. 'pip install pymupdf' 후 다시 실행하세요."
        )
    config = config or OcrConfig()
    cancel_check = cancel_check or (lambda: False)
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {path}")

    engine = ocr_engine or OcrEngine(models_dir=models_dir, config=config)
    doc = fitz.open(path)
    pages: List[PageText] = []
    try:
        total = doc.page_count
        for index in range(total):
            if cancel_check():
                break
            page = doc[index]
            _progress(progress, f"{index + 1}/{total}쪽 텍스트 확인", index, total)
            native = _page_text_native(page)
            needs = config.force_ocr or page_needs_ocr(page, native, config.min_text_chars)
            if not needs:
                pages.append(PageText(index + 1, _normalize_text(native), False))
                continue
            _progress(progress, f"{index + 1}/{total}쪽 OCR 인식", index, total)
            try:
                ocr_text = engine.recognize_page(page)
            except OcrUnavailable:
                raise
            except Exception as exc:
                ocr_text = ""
                _progress(progress, f"{index + 1}쪽 OCR 실패: {exc}", index, total)
            text = ocr_text if len(ocr_text.strip()) >= len(native.strip()) else native
            pages.append(PageText(index + 1, _normalize_text(text), used_ocr=True))
    finally:
        doc.close()
    return pages


def pages_to_text(pages: List[PageText], page_separator: str = "\n\n\f\n\n") -> str:
    return page_separator.join(page.text.strip("\n") for page in pages)
