"""pytest 공통 준비물 — 샘플 한국어 법률문서(PDF/스캔본) 생성."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FONT_CANDIDATES = [
    "/usr/share/fonts/pickle-hwp/NotoSansCJKkr-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
    "C:/Windows/Fonts/malgun.ttf",
]


def korean_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    pytest.skip("한국어 폰트를 찾지 못해 샘플 PDF를 만들 수 없습니다.")


SAMPLE_TEXT = """서울중앙지방법원 제3민사부
판 결
사건 2020가합12345 손해배상(기)
원고 김민수
서울특별시 강남구 테헤란로 123, 4층 402호
피고 주식회사 한빛테크
대표이사 이재훈
1. 원고의 청구를 기각한다.
2. 소송비용은 원고가 부담한다.
민법 제750조 및 상법 제65조, 대법원 2020다12345 판결 참조.
"""


@pytest.fixture(scope="session")
def sample_text() -> str:
    return SAMPLE_TEXT


@pytest.fixture(scope="session")
def text_pdf(tmp_path_factory) -> Path:
    import pymupdf as fitz

    path = tmp_path_factory.mktemp("fixtures") / "판결문_샘플.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rc = page.insert_textbox(
        fitz.Rect(50, 50, 545, 792),
        SAMPLE_TEXT,
        fontsize=12,
        fontfile=korean_font(),
        fontname="NotoKR",
    )
    assert rc >= 0
    doc.save(path)
    doc.close()
    return path


@pytest.fixture(scope="session")
def scanned_pdf(tmp_path_factory) -> Path:
    import pymupdf as fitz
    from PIL import Image, ImageDraw, ImageFont

    path = tmp_path_factory.mktemp("fixtures") / "스캔본_샘플.pdf"
    image = Image.new("RGB", (1654, 2339), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(korean_font(), 36)
    y = 150
    for line in SAMPLE_TEXT.splitlines():
        draw.text((150, y), line, font=font, fill="black")
        y += 70
    png = path.with_suffix(".png")
    image.save(png)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(0, 0, 595, 842), filename=str(png))
    doc.save(path)
    doc.close()
    return path
