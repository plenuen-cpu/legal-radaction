"""비식별화 엔진(치환 일관성·가드·LLM 연동) 테스트."""
from __future__ import annotations

import deidentifier as D


class FakeLlm:
    """테스트용 LLM — 정해진 개체만 돌려준다."""

    def __init__(self, entities):
        self.entities = entities
        self.calls = []

    def extract_entities(self, chunk):
        self.calls.append(chunk)
        return [e for e in self.entities if e["text"] in chunk]


def run(text, llm=None, use_llm=True, style="pseudonym"):
    engine = D.Deidentifier(style=style, llm=llm, use_llm=use_llm, chunk_size=100000)
    return engine.process(text)


def test_same_person_gets_same_placeholder():
    text = "원고 김민수는 주장했다. 증인 김민수는 그 주장을 뒷받침했다."
    result = run(text)
    assert "김민수" not in result.text
    assert result.text.count("[이름1]") == 2
    assert len(result.table) == 1


def test_two_people_get_ordered_numbers():
    text = "원고 김민수와 피고 이재훈이 출석했다."
    result = run(text)
    assert "[이름1]" in result.text
    assert "[이름2]" in result.text
    assert "김민수" not in result.text
    assert "이재훈" not in result.text


def test_mask_style_uses_asterisks():
    text = "원고 김민수, 연락처 010-1234-5678"
    result = run(text, style="mask")
    assert "김민수" not in result.text
    assert "010-1234-5678" not in result.text
    assert "***" in result.text


def test_structured_pii_masked_without_llm():
    text = (
        "주민등록번호 900101-1234568, 전화 010-1234-5678, 메일 a@b.co.kr, "
        "계좌번호: 110-123-456789, 차량 12가3456"
    )
    result = run(text, use_llm=False)
    for leaked in ("900101-1234568", "010-1234-5678", "a@b.co.kr", "110-123-456789", "12가3456"):
        assert leaked not in result.text
    assert result.stats["RRN"] == 1
    assert result.stats["PHONE"] == 1


def test_law_court_and_case_number_preserved():
    text = "서울중앙지방법원 제3민사부는 민법 제750조, 대법원 2020다12345 판결을 인용했다."
    result = run(text, use_llm=False)
    for kept in ("서울중앙지방법원", "제3민사부", "민법 제750조", "2020다12345"):
        assert kept in result.text


def test_mapping_table_contents():
    text = "원고 김민수(900101-1234568)"
    result = run(text)
    rows = result.table.rows()
    originals = {row["원문"] for row in rows}
    assert "김민수" in originals
    assert any("900101" in value for value in originals)
    for row in rows:
        assert row["번호"] >= 1
        assert row["유형"]
        assert row["대체표시"]


def test_llm_adds_context_name_and_org():
    text = "김민수는 한빛테크에 입사했다. 김민수는 서울 강남구에 산다."
    llm = FakeLlm(
        [
            {"type": "PERSON", "text": "김민수"},
            {"type": "ORG", "text": "한빛테크"},
        ]
    )
    result = run(text, llm=llm)
    assert llm.calls, "LLM이 호출되어야 한다"
    assert "김민수" not in result.text
    assert "한빛테크" not in result.text
    assert "[이름1]" in result.text
    assert "[회사1]" in result.text


def test_llm_cannot_remove_court_or_law():
    text = "대법원은 민법 제750조를 적용했다. 김민수는 패소했다."
    llm = FakeLlm(
        [
            {"type": "PERSON", "text": "대법원"},
            {"type": "PERSON", "text": "김민수"},
            {"type": "ORG", "text": "민법"},
            {"type": "ADDRESS", "text": "2020가합12345"},
        ]
    )
    result = run(text, llm=llm)
    assert "대법원" in result.text
    assert "민법" in result.text
    assert "김민수" not in result.text


def test_llm_hallucination_ignored():
    text = "원고는 주장했다."
    llm = FakeLlm([{"type": "PERSON", "text": "없는사람"}])
    result = run(text, llm=llm)
    assert "없는사람" not in result.text
    assert len(result.table) == 0


def test_llm_entity_masked_even_with_wrong_type():
    text = "한빛테크가 계약했다."
    llm = FakeLlm([{"type": "PERSON", "text": "한빛테크"}])
    result = run(text, llm=llm)
    # 라벨이 틀려도 개인정보는 높였는지가 중요하다(이름으로 처리됨)
    assert "한빛테크" not in result.text


def test_particle_name_refinement_uses_document_frequency():
    text = "대표이사 이재훈은 입장을 밝혔다. 증인 이재훈은 증인이다. 이재훈의 진술."
    result = run(text, use_llm=False)
    assert "이재훈" not in result.text
    assert "[이름1]" in result.text
    originals = [row["원문"] for row in result.table.rows()]
    assert "이재훈" in originals
    assert all("은" not in name for name in originals)


def test_name_ending_in_particle_letter_preserved():
    # '김정은'처럼 이름 자체가 '은'으로 끝나면 문서 빈도상 잘리지 않는다
    text = "증인 김정은은 등장했다. 증인 김정은의 발언."
    result = run(text, use_llm=False)
    assert "김정은" not in result.text
    assert any(row["원문"] == "김정은" for row in result.table.rows())


def test_warning_when_llm_missing():
    result = run("원고 김민수", use_llm=True, llm=None)
    assert any("AI 모델" in w or "정형 패턴만" in w for w in result.warnings)


def test_newlines_and_page_separator_kept():
    text = "원고 김민수\n\n\f\n\n피고 이재훈"
    result = run(text, use_llm=False)
    assert "\f" in result.text


def test_chunk_splitter_respects_size():
    text = ("가" * 300 + "\n\n") * 10
    chunks = D.split_chunks(text, 1200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1300 for chunk in chunks)


def test_llm_failure_does_not_break_processing():
    class BrokenLlm:
        def extract_entities(self, chunk):
            raise RuntimeError("모델 오류")

    text = "원고 김민수, 900101-1234568"
    result = run(text, llm=BrokenLlm())
    assert "900101-1234568" not in result.text
    assert any("AI 분석 실패" in warning for warning in result.warnings)
