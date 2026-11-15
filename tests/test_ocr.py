"""PDF 텍스트 추출·OCR 연동 테스트."""
from __future__ import annotations

from pathlib import Path

import pytest

import ocr_pipeline
from paths import bundled_ocr_models_dir


def test_text_pdf_uses_native_extraction(text_pdf):
    pages = ocr_pipeline.extract_pages(text_pdf)
    assert len(pages) == 1
    page = pages[0]
    assert page.used_ocr is False
    assert "서울중앙지방법원" in page.text
    assert "김민수" in page.text
    # PDF의 비분리 공백이 일반 공백으로 정리된다
    assert "\u00a0" not in page.text


def test_scanned_pdf_needs_ocr(scanned_pdf):
    import pymupdf as fitz

    doc = fitz.open(scanned_pdf)
    try:
        text = doc[0].get_text("text")
        assert ocr_pipeline.page_needs_ocr(doc[0], text) is True
    finally:
        doc.close()


@pytest.mark.slow
def test_scanned_pdf_ocr_korean(scanned_pdf):
    # 메모리·시간을 아끼기 위해 200 DPI로 인식
    pages = ocr_pipeline.extract_pages(
        scanned_pdf, config=ocr_pipeline.OcrConfig(dpi=200), models_dir=bundled_ocr_models_dir()
    )
    assert pages[0].used_ocr is True
    text = pages[0].text
    assert "서울중앙지방법원" in text.replace(" ", "")
    assert "김민수" in text.replace(" ", "")
    assert "한빛테크" in text.replace(" ", "")


def test_bundled_ocr_models_present():
    directory = bundled_ocr_models_dir()
    assert directory is not None, "models/ocr에 OCR 모델이 함께 배포되어야 한다"
    names = " ".join(path.name for path in directory.glob("*.onnx"))
    assert "det" in names
    assert "korean" in names


def test_ocr_engine_resolves_local_models():
    engine = ocr_pipeline.OcrEngine(models_dir=bundled_ocr_models_dir())
    paths = engine._model_paths()
    assert set(paths) >= {"det", "rec"}


def test_join_ocr_lines_cleans_spacing():
    lines = ["  원고   김민수 ", "", "피고 [회사1]"]
    assert ocr_pipeline.join_ocr_lines(lines) == "원고 김민수\n피고 [회사1]"


def test_pages_to_text_keeps_page_separator():
    pages = [ocr_pipeline.PageText(1, "첫째"), ocr_pipeline.PageText(2, "둘째")]
    assert "\f" in ocr_pipeline.pages_to_text(pages)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ocr_pipeline.extract_pages(tmp_path / "없는파일.pdf")


def test_force_ocr_option(text_pdf):
    engine = ocr_pipeline.OcrEngine(
        models_dir=bundled_ocr_models_dir(), config=ocr_pipeline.OcrConfig(dpi=150)
    )
    pages = ocr_pipeline.extract_pages(
        text_pdf,
        config=ocr_pipeline.OcrConfig(force_ocr=True, dpi=150),
        ocr_engine=engine,
    )
    assert pages[0].used_ocr is True
    assert "김민수" in pages[0].text.replace(" ", "")
