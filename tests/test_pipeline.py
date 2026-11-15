"""전체 파이프라인(PDF → TXT/DOCX/대조표) 테스트."""
from __future__ import annotations

from pathlib import Path

import config
import pipeline


def test_end_to_end_without_llm(text_pdf, tmp_path):
    cfg = config.PipelineConfig(use_llm=False, save_mapping=True)
    result = pipeline.process_pdf(text_pdf, cfg, output_dir=tmp_path, progress=lambda *a: None)

    assert result.ok, result.error
    assert result.page_count == 1
    assert result.txt_path.exists()
    assert result.docx_path.exists()
    assert result.mapping_path and result.mapping_path.exists()

    text = result.txt_path.read_text(encoding="utf-8-sig")
    assert "[이름1]" in text
    assert "[회사1]" in text
    for leaked in ("김민수", "이재훈", "한빛테크", "테헤란로", "2020가합12345"):
        if leaked == "2020가합12345":
            assert leaked in text  # 사건번호는 유지
        else:
            assert leaked not in text
    # 법원·법령은 유지
    assert "서울중앙지방법원" in text
    assert "민법 제750조" in text
    assert "대법원 2020다12345" in text
    assert "요약" not in text  # 요약본이 아니라 원문 구조 유지


def test_outputs_go_to_requested_folder(text_pdf, tmp_path):
    target = tmp_path / "결과" / "2026"
    result = pipeline.process_pdf(
        text_pdf, config.PipelineConfig(use_llm=False), output_dir=target
    )
    assert result.ok
    assert result.txt_path.parent == target
    assert target.exists()


def test_mapping_can_be_disabled(text_pdf, tmp_path):
    result = pipeline.process_pdf(
        text_pdf,
        config.PipelineConfig(use_llm=False, save_mapping=False),
        output_dir=tmp_path,
    )
    assert result.ok
    assert result.mapping_path is None


def test_non_pdf_rejected(tmp_path):
    other = tmp_path / "문서.txt"
    other.write_text("내용", encoding="utf-8")
    result = pipeline.process_pdf(other, config.PipelineConfig(use_llm=False), output_dir=tmp_path)
    assert not result.ok
    assert "PDF" in result.error


def test_missing_pdf_reports_error(tmp_path):
    result = pipeline.process_pdf(
        tmp_path / "없음.pdf", config.PipelineConfig(use_llm=False), output_dir=tmp_path
    )
    assert not result.ok
    assert "찾을 수 없습니다" in result.error


def test_summary_contains_counts(text_pdf, tmp_path):
    result = pipeline.process_pdf(
        text_pdf, config.PipelineConfig(use_llm=False), output_dir=tmp_path
    )
    summary = pipeline.summarize(result)
    assert "1쪽" in summary
    assert "이름" in summary


def test_mask_style_end_to_end(text_pdf, tmp_path):
    cfg = config.PipelineConfig(use_llm=False, style=config.STYLE_MASK)
    result = pipeline.process_pdf(text_pdf, cfg, output_dir=tmp_path)
    text = result.txt_path.read_text(encoding="utf-8-sig")
    assert "***" in text
    assert "김민수" not in text
