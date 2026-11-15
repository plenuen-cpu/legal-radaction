"""TXT / DOCX / 대조표 출력 테스트."""
from __future__ import annotations

import csv

from docx import Document
from docx.oxml.ns import qn

import exporter


def test_txt_saved_with_bom(tmp_path):
    path = exporter.export_txt("첫 줄\n둘째 줄", tmp_path / "결과.txt")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "첫 줄" in raw.decode("utf-8-sig")


def test_docx_keeps_paragraphs_and_korean_font(tmp_path):
    text = "서울중앙지방법원\n\n원고 [이름1]\n피고 [회사1]"
    path = exporter.export_docx(text, tmp_path / "결과.docx")
    document = Document(path)
    contents = [p.text for p in document.paragraphs]
    assert "서울중앙지방법원" in contents
    assert "원고 [이름1]" in contents
    style = document.styles["Normal"]
    rfonts = style.element.get_or_add_rPr().find(qn("w:rFonts"))
    assert rfonts.get(qn("w:eastAsia")) == exporter.DEFAULT_FONT


def test_docx_page_break_between_pages(tmp_path):
    path = exporter.export_docx("1쪽 내용\n\f\n2쪽 내용", tmp_path / "쪽나눔.docx")
    xml = Document(path).element.xml
    assert 'w:type="page"' in xml


def test_mapping_csv(tmp_path):
    rows = [
        {"번호": 1, "유형": "이름", "원문": "김민수", "대체표시": "[이름1]", "등장횟수": 3},
    ]
    path = exporter.export_mapping_csv(rows, tmp_path / "대조표.csv")
    assert path is not None
    with path.open(encoding="utf-8-sig", newline="") as handle:
        data = list(csv.DictReader(handle))
    assert data[0]["원문"] == "김민수"
    assert data[0]["대체표시"] == "[이름1]"


def test_empty_mapping_returns_none(tmp_path):
    assert exporter.export_mapping_csv([], tmp_path / "없음.csv") is None


def test_unique_path_avoids_overwrite(tmp_path):
    first = tmp_path / "결과.txt"
    first.write_text("원본", encoding="utf-8")
    second = exporter.unique_path(first)
    assert second != first
    assert second.name.startswith("결과 (")


def test_output_paths_use_korean_suffix(tmp_path):
    paths = exporter.build_output_paths(tmp_path / "판결문.pdf", tmp_path)
    assert paths["txt"].name == "판결문_비식별화.txt"
    assert paths["docx"].name == "판결문_비식별화.docx"
    assert paths["mapping"].name == "판결문_비식별화_대조표.csv"
