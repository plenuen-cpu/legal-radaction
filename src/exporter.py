"""비식별화 결과를 TXT / DOCX(워드) / 치환 대조표(CSV)로 저장."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable, List, Optional

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

DEFAULT_FONT = "맑은 고딕"
PAGE_SEPARATOR = "\f"


def unique_path(path: Path) -> Path:
    """이미 있으면 '이름 (2).ext'처럼 새 경로를 만든다(원본 덮어쓰기 방지)."""
    path = Path(path)
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
    return path


def export_txt(text: str, path: Path) -> Path:
    path = unique_path(Path(path))
    path.write_text(text, encoding="utf-8-sig", newline="\n")
    return path


def _set_default_font(document: Document, font_name: str = DEFAULT_FONT, size_pt: float = 10.5) -> None:
    style = document.styles["Normal"]
    style.font.name = font_name
    style.font.size = Pt(size_pt)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font_name)


def _add_page_number_footer(document: Document) -> None:
    section = document.sections[0]
    paragraph = section.footer.paragraphs[0]
    paragraph.text = ""
    run = paragraph.add_run()
    for field in ("PAGE",):
        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = f" {field} "
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        run._r.append(begin)
        run._r.append(instr)
        run._r.append(end)


def export_docx(
    text: str,
    path: Path,
    font_name: str = DEFAULT_FONT,
    add_notice: bool = False,
    page_numbers: bool = True,
) -> Path:
    """문단 구조를 살린 한국어 워드 문서로 저장한다."""
    path = unique_path(Path(path))
    document = Document()
    _set_default_font(document, font_name)
    for section in document.sections:
        section.top_margin = section.top_margin
    if page_numbers:
        try:
            _add_page_number_footer(document)
        except Exception:
            pass

    pages = text.split(PAGE_SEPARATOR)
    for page_index, page in enumerate(pages):
        lines = page.split("\n")
        for line in lines:
            rstrip_line = line.rstrip("\r")
            paragraph = document.add_paragraph()
            fmt = paragraph.paragraph_format
            fmt.space_before = Pt(0)
            fmt.space_after = Pt(0)
            fmt.line_spacing = 1.35
            if rstrip_line.strip():
                paragraph.add_run(rstrip_line)
        if page_index < len(pages) - 1:
            document.add_page_break()

    if add_notice:
        document.add_paragraph()
        notice = document.add_paragraph()
        run = notice.add_run(
            "※ 이 문서는 개인정보 보호를 위해 자동 비식별화 처리되었습니다. "
            "치환 결과는 원문과 대조하여 확인하세요."
        )
        run.italic = True
        run.font.size = Pt(8.5)

    document.save(path)
    return path


def export_mapping_csv(rows: Iterable[dict], path: Path) -> Optional[Path]:
    """치환 대조표를 엑셀에서 바로 열 수 있는 CSV(UTF-8 BOM)로 저장."""
    rows = list(rows)
    if not rows:
        return None
    path = unique_path(Path(path))
    fieldnames: List[str] = ["번호", "유형", "원문", "대체표시", "등장횟수"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return path


def build_output_paths(pdf_path: Path, output_dir: Path, base_name: str = "비식별화") -> dict:
    stem = re.sub(r"[\\/:*?\"<>|]+", "_", Path(pdf_path).stem)
    output_dir = Path(output_dir)
    return {
        "txt": output_dir / f"{stem}_{base_name}.txt",
        "docx": output_dir / f"{stem}_{base_name}.docx",
        "mapping": output_dir / f"{stem}_{base_name}_대조표.csv",
    }
