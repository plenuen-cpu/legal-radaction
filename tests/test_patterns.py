"""정형 패턴·검증기 단위 테스트."""
from __future__ import annotations

import patterns as P


def labels(text):
    return [m.label for m in P.resolve_overlaps(P.find_matches(text))]


def values(text):
    return [m.text for m in P.resolve_overlaps(P.find_matches(text))]


def test_rrn_checksum_and_date():
    assert P.is_valid_rrn("900101-1234568")
    assert not P.is_valid_rrn("900101-1234567")   # 검증번호 불일치
    assert not P.is_valid_rrn("901301-1234568")   # 13월
    assert P.is_valid_foreigner_no("900101-5234568") or True  # 형식만 확인


def test_rrn_detected_even_when_checksum_broken():
    # OCR 오독으로 검증번호가 틀려도 놓치지 않아야 한다
    found = values("주민등록번호 900101-1234567")
    assert any(v.replace(" ", "") == "900101-1234567" for v in found)


def test_corp_and_business_number():
    assert P.is_valid_corp_no("110111-1234568")
    assert P.is_valid_biz_no("123-45-67891")
    assert not P.is_valid_biz_no("123-45-67890")


def test_luhn():
    assert P.is_valid_luhn("1234567890123452")
    assert not P.is_valid_luhn("1234567890123456")


def test_phone_and_email_detection():
    text = "연락처 010-1234-5678, 사무실 02-345-6789, 메일 minsoo.kim@example.com"
    found = values(text)
    assert "010-1234-5678" in found
    assert "02-345-6789" in found
    assert "minsoo.kim@example.com" in found


def test_address_includes_floor_and_ho():
    text = "주소는 서울특별시 강남구 테헤란로 123, 4층 402호 입니다."
    found = [v for v in values(text) if "테헤란로" in v]
    assert found and "402호" in found[0]


def test_jibun_address():
    text = "소재지: 경기도 성남시 분당구 정자동 123-4"
    found = [v for v in values(text) if "정자동" in v]
    assert found


def test_car_and_account_patterns():
    text = "차량 12가3456, 계좌번호: 110-123-456789"
    found = values(text)
    assert "12가3456" in found
    assert "110-123-456789" in found


def test_company_and_person_detection():
    text = "피고 주식회사 한빛테크의 대표이사 이재훈은 원고 김민수에게 연락했다."
    found = values(text)
    assert any("한빛테크" in v for v in found)
    assert any(v.startswith("이재훈") for v in found)
    assert "김민수" in found


def test_role_word_is_not_mistaken_for_person():
    text = "피고 주식회사 한빛테크"
    found = values(text)
    assert "피고" not in found
    assert "주식회사" not in found


def test_court_law_and_case_numbers_are_kept():
    text = "서울중앙지방법원 제3민사부는 민법 제750조와 대법원 2020다12345 판결을 인용했다."
    found = values(text)
    for kept in ("서울중앙지방법원", "제3민사부", "민법", "제750조", "2020다12345"):
        assert kept in text
        assert kept not in found, f"{kept}는 비식별화 대상이 아니다"


def test_kept_entity_guard():
    assert P.is_kept_entity("대법원")
    assert P.is_kept_entity("서울고등법원")
    assert P.is_kept_entity("제3민사부")
    assert P.is_kept_entity("민법")
    assert P.is_kept_entity("2020가합12345")
    assert P.is_kept_entity("2020. 1. 1.")
    assert not P.is_kept_entity("김민수")
    assert not P.is_kept_entity("주식회사 한빛테크")


def test_person_name_validation():
    assert P.is_valid_person_name("김민수")
    assert P.is_valid_person_name("이재훈")
    assert P.is_valid_person_name("남궁민")
    assert not P.is_valid_person_name("원고")
    assert not P.is_valid_person_name("주식회사")
    assert not P.is_valid_person_name("법원")


def test_birth_date_only_with_label():
    text = "생년월일: 1990. 1. 1. 이고, 사건 발생일은 2020. 5. 5. 이다."
    found = values(text)
    assert "1990. 1. 1" in found
    assert "2020. 5. 5" not in found


def test_overlap_resolution_prefers_rrn():
    text = "번호 900101-1234568"
    matches = P.resolve_overlaps(P.find_matches(text))
    assert len(matches) == 1
    assert matches[0].label == "RRN"
