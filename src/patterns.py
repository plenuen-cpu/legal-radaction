"""한국어 법률문서 비식별화용 정형(정규식) 패턴과 검증기.

1단계 엔진은 여기의 규칙만으로 100% 결정적으로 동작한다.
LLM이 없어도 주민등록번호·전화·이메일·계좌·카드·사업자번호·차량번호·주소 등은 모두 잡힌다.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

# --------------------------------------------------------------------------
# 검증기
# --------------------------------------------------------------------------


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def is_valid_rrn(value: str) -> bool:
    """주민등록번호 검증(생년월일 + 검증번호)."""
    d = digits_only(value)
    if len(d) != 13:
        return False
    yy, mm, dd = int(d[0:2]), int(d[2:4]), int(d[4:6])
    gender = int(d[6])
    if gender in (1, 2, 5, 6):
        year = 1900 + yy
    elif gender in (3, 4, 7, 8):
        year = 2000 + yy
    else:
        return False
    try:
        _dt.date(year, mm, dd)
    except ValueError:
        return False
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    total = sum(int(d[i]) * weights[i] for i in range(12))
    if gender in (5, 6, 7, 8):  # 외국인등록번호는 +2 보정
        total += 2
    check = (11 - total % 11) % 10
    return check == int(d[12])


def is_valid_foreigner_no(value: str) -> bool:
    d = digits_only(value)
    return len(d) == 13 and d[6] in "5678" and is_valid_rrn(value)


def is_plausible_rrn(value: str) -> bool:
    """형식상 주민등록번호로 보이는지(생년월일·성별자리).

    OCR 오독으로 검증번호가 틀려도 놓치지 않도록 탐지 단계에서는
    검증번호를 요구하지 않는다.
    """
    d = digits_only(value)
    if len(d) != 13:
        return False
    yy, mm, dd = int(d[0:2]), int(d[2:4]), int(d[4:6])
    gender = int(d[6])
    if gender in (1, 2, 5, 6):
        year = 1900 + yy
    elif gender in (3, 4, 7, 8):
        year = 2000 + yy
    else:
        return False
    try:
        _dt.date(year, mm, dd)
    except ValueError:
        return False
    return True


def is_valid_corp_no(value: str) -> bool:
    """법인등록번호(13자리) 검증."""
    d = digits_only(value)
    if len(d) != 13:
        return False
    weights = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for i in range(12):
        v = int(d[i]) * weights[i]
        total += v if v < 10 else v - 9
    return (10 - total % 10) % 10 == int(d[12])


def is_valid_biz_no(value: str) -> bool:
    """사업자등록번호(10자리) 검증."""
    d = digits_only(value)
    if len(d) != 10:
        return False
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = sum(int(d[i]) * weights[i] for i in range(9))
    total += (int(d[8]) * 5) // 10
    return (10 - total % 10) % 10 == int(d[9])


def is_valid_luhn(value: str) -> bool:
    d = digits_only(value)
    if not 13 <= len(d) <= 19:
        return False
    total = 0
    reverse = d[::-1]
    for idx, ch in enumerate(reverse):
        n = int(ch)
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def looks_like_date(value: str) -> bool:
    d = digits_only(value)
    if len(d) != 8:
        return False
    try:
        _dt.date(int(d[0:4]), int(d[4:6]), int(d[6:8]))
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------
# 이름 판별 보조 자료
# --------------------------------------------------------------------------

SURNAMES = set(
    "김이박최정강조윤장임한오서신권황안송류유홍전고문양손배백허남심노하곽성차주우구민진나지엄채원천방공현함변염여추도석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예경봉사부소담황보남궁제갈선우독고동방서문사공"
)
COMPOUND_SURNAMES = {
    "남궁", "황보", "제갈", "선우", "독고", "동방", "서문", "사공", "어금", "장곡", "망절",
}

# 이름으로 오인하면 안 되는 법률·일반 용어
NAME_STOPWORDS = {
    "원고", "피고", "피고인", "피의자", "피해자", "고소인", "고발인", "증인", "참고인",
    "신청인", "상대방", "대표", "대표이사", "이사", "직원", "근로자", "사용자", "계약자",
    "임차인", "임대인", "매수인", "매도인", "채권자", "채무자", "보증인", "상속인",
    "유언자", "망인", "법원", "판사", "검사", "변호사", "법무사", "당사자", "제3자",
    "선생", "고객", "회원", "사장", "담당", "기사", "박사", "교수", "의사", "부장",
    "과장", "팀장", "대리", "주무관", "관계자", "가해자", "목격자", "신고자", "제보자",
    "본인", "배우자", "부모", "자녀", "형제", "친족", "가족", "회사", "기관", "단체",
    "대한민국", "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
    "법인", "개인", "상호", "명의", "성명", "주소", "연락처", "내용", "사실", "경우",
    "관련", "이상", "이하", "기타", "등등", "다음", "당시", "현재", "향후", "이후",
    "주식회사", "유한회사", "합자회사", "합명회사", "사단법인", "재단법인",
    "법무법인", "변호사", "법률사무소", "노무법인", "회계법인", "세무법인",
}

# 역할 표지(이름 앞에 오는 말) — 회사명 오탐 방지에도 사용
ROLE_WORDS = {
    "원고", "피고", "피고인", "피의자", "피해자", "고소인", "고발인", "증인",
    "참고인", "신청인", "상대방", "대표", "대표이사", "이사", "직원", "근로자",
    "사용자", "계약자", "임차인", "임대인", "매수인", "매도인", "채권자", "채무자",
    "보증인", "상속인", "유언자", "망인", "당사자", "제3자", "담당", "담당자",
    "실무자", "책임자", "관리자", "신고인", "진술인", "목격자", "유족", "법정대리인",
}

COMPANY_FORMS = (
    "주식회사", "유한회사", "합자회사", "합명회사", "유한책임회사",
    "사단법인", "재단법인", "영농조합법인", "협동조합", "사회적협동조합",
)

# 비식별화하면 안 되는 공공기관(법원·검찰·경찰·행정기관)
KEEP_INSTITUTION_RE = re.compile(
    r"(?:대법원|헌법재판소|특허법원|"
    r"[가-힣]{2,10}법원|"
    r"[가-힣]{2,10}지원|"
    r"[가-힣]{2,10}검찰청|"
    r"[가-힣]{2,10}경찰서|"
    r"[가-힣]{2,10}경찰청|"
    r"법무부|법원행정처|대한법률구조공단|국가인권위원회|금융위원회|금융감독원|"
    r"공정거래위원회|개인정보보호위원회|국세청|관세청|병무청|경찰청|소방청|감사원|"
    r"국민권익위원회|중앙노동위원회|중앙행정심판위원회|대검찰청|고등검찰청|"
    r"보건복지부|고용노동부|국토교통부|법제처|통계청|행정안전부|기획재정부|외교부|"
    r"교육부|과학기술정보통신부|문화체육관광부|농림축산식품부|산업통상자원부|"
    r"환경부|여성가족부|해양수산부|중소벤처기업부|인사혁신처|식품의약품안전처)"
)

COURT_DIVISION_RE = re.compile(
    r"제?\s*\d+\s*(?:민사|형사|행정|가사|특허|회생|소년)\d*\s*부|"
    r"[가-힣]{0,6}(?:민사|형사|행정|가사|특허|회생)\s*\d*\s*단독"
)

LAW_WORD_RE = re.compile(
    r"^(?:[가-힣]{1,15}(?:법|법률|령|규칙|조례|헌법|조약|협약))$|"
    r"제\s*\d+\s*조(?:의\s*\d+)?|제\s*\d+\s*항|제\s*\d+\s*호"
)

CASE_NO_RE = re.compile(
    r"\d{2,4}\s*(?:가합|가단|가소|나|다|라|마|바|사|아|자|카|카합|카단|구합|구단|허|"
    r"재나|재다|재가합|헌[가-힣]|초|오|모|푸|그|드|즈|스)\s*\d{1,7}"
)

GENERIC_ORG_STOPWORDS = {
    "회사", "법인", "기관", "단체", "상사", "업체", "거래처", "회사명", "상호명",
    "원고회사", "피고회사", "주식회사", "유한회사", "사단법인", "재단법인",
    "법원", "검찰", "경찰", "은행", "보험회사", "증권회사",
}

# 주소로 인정하기 위한 최소 조건: 숫자 + 주소 토큰
ADDRESS_TOKEN_RE = re.compile(r"(?:로|길|대로|번길|동|읍|면|리|번지|호|층|아파트|빌라|오피스텔|빌딩)")

PLACEHOLDER_RE = re.compile(r"\[\s*(?:이름|주소|회사|기관|전화|이메일|주민번호|외국인번호|법인번호|사업자번호|계좌|카드|차량|여권|면허|생년월일|IP|기타)\s*\d*\s*\]")


# --------------------------------------------------------------------------
# 규칙 정의
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    name: str
    label: str
    pattern: re.Pattern
    group: int = 0
    validator: Optional[Callable[[str], bool]] = None
    post_filter: Optional[Callable[[str, str, int, int], bool]] = None
    trim: Optional[Callable[[str], str]] = None
    priority: int = 100


@dataclass
class Match:
    start: int
    end: int
    text: str
    label: str
    rule: str
    priority: int = 100


def _road_ok(value: str) -> bool:
    """도로명 단독 패턴의 오탐(가로/대로 같은 일반명사) 방지."""
    head = value.split()[0]
    return len(head) >= 3 and head not in {"가로", "세로", "대로", "통로", "인도", "차도", "횡로", "진입로"}


def _name_ok(name: str, text: str = "", start: int = 0, end: int = 0) -> bool:
    name = name.strip()
    if not (2 <= len(name) <= 4):
        return False
    if not re.fullmatch(r"[가-힣]+", name):
        return False
    if name in NAME_STOPWORDS or name in ROLE_WORDS:
        return False
    if any(form in name for form in COMPANY_FORMS):
        return False
    if name[0] in "제각본상하전후중신구" and len(name) <= 2:
        return False
    if name.endswith(("법", "원", "청", "부", "처", "국", "회", "단", "팀", "실", "소", "관")):
        return False
    return name[0] in SURNAMES or name[:2] in COMPOUND_SURNAMES


def _corp_name_ok(value: str, text: str = "", start: int = 0, end: int = 0) -> bool:
    cleaned = value.strip()
    if len(cleaned) < 2 or len(cleaned) > 60:
        return False
    if cleaned in GENERIC_ORG_STOPWORDS or cleaned in ROLE_WORDS or cleaned in NAME_STOPWORDS:
        return False
    if any(cleaned.startswith(form) and len(cleaned) <= len(form) + 1 for form in COMPANY_FORMS):
        return False
    if KEEP_INSTITUTION_RE.fullmatch(cleaned):
        return False
    return True


def _address_ok(value: str, text: str = "", start: int = 0, end: int = 0) -> bool:
    return bool(re.search(r"\d", value)) and bool(ADDRESS_TOKEN_RE.search(value))


_PARTICLES = (
    "으로서", "으로써", "에서는", "에게는", "으로", "에서", "에게", "부터", "까지",
    "이라고", "라고", "은", "는", "이", "가", "을", "를", "의", "에",
    "와", "과", "도", "만", "로", "께", "측", "등", "란", "라는",
)


def trim_particle(value: str) -> str:
    """회사명 등 뒤에 붙은 조사를 잘라낸다("한빛테크의" → "한빛테크")."""
    out = value.rstrip(" \t,.;:)")
    for _ in range(2):
        changed = False
        for particle in _PARTICLES:
            if out.endswith(particle) and len(out) - len(particle) >= 2:
                candidate = out[: -len(particle)]
                if candidate and re.search(r"[가-힣A-Za-z0-9]", candidate):
                    out = candidate
                    changed = True
                    break
        if not changed:
            break
    return out


def _card_ok(value: str, text: str = "", start: int = 0, end: int = 0) -> bool:
    """카드번호: 구분자가 있거나 Luhn 검증을 통과해야 한다."""
    if re.search(r"[-\s]", value.strip()):
        return True
    return is_valid_luhn(value)


def trim_corp(value: str) -> str:
    """'주식회사 한빛테크의 대표이사' → '주식회사 한빛테크'."""
    out = value.strip()
    tokens = out.split()
    if len(tokens) >= 3:
        extra = tokens[-1]
        if (
            extra in ROLE_WORDS
            or extra in NAME_STOPWORDS
            or extra in GENERIC_ORG_STOPWORDS
            or extra.endswith(("은", "는", "이", "가", "을", "를", "의", "에"))
        ):
            out = " ".join(tokens[:-1])
    return trim_particle(out)


# 주민등록번호 / 외국인등록번호 / 법인등록번호 (모두 6-7 형식)
_RRN_RE = re.compile(r"(?<!\d)(\d{6})\s*[-–—]\s*(\d{7})(?!\d)")

# 사업자등록번호
_BIZ_RE = re.compile(r"(?<!\d)(\d{3})\s*-\s*(\d{2})\s*-\s*(\d{5})(?!\d)")

# 카드번호(16자리, 4-4-4-4 또는 붙여쓰기)
_CARD_RE = re.compile(r"(?<!\d)(?:\d{4}[-\s]?){3}\d{4}(?!\d)")

# 휴대전화 (+82 10-1234-5678, 010.1234.5678 포함)
_MOBILE_RE = re.compile(
    r"(?<![\d+])(?:\+?\s?82[-\s.]?)?(?:0?1[016789])[-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)"
)

# 일반전화/팩스 (02-123-4567, 031-123-4567, 02)123-4567)
_LANDLINE_RE = re.compile(r"(?<![\d+])0(?:2|[3-6]\d)[-)\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)")

_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])")

# 여권번호
_PASSPORT_RE = re.compile(r"(?<![A-Za-z0-9])(?:[MSRODmsrod]\d{8})(?![A-Za-z0-9])")

# 운전면허번호
_LICENSE_RE = re.compile(r"(?<!\d)\d{2}-\d{2}-\d{6}-\d{2}(?!\d)")

# 차량번호(공백 없이 붙어 쓰인 경우만 — "101동 1002호" 오탐 방지)
_VEHICLE_RE = re.compile(r"(?<!\d)(?:\d{2,3}[가-힣]\d{4})(?!\d)")

# IP 주소
_IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")

# 상세 주소(시·도 + 시·군·구 + 도로명/지번)
_SIDO = "서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주"
_ADDRESS_FULL_RE = re.compile(
    rf"(?<![가-힣])(?:{_SIDO})(?:특별시|광역시|특별자치시|특별자치도|도|시)?\s+"
    r"(?:[가-힣]{2,10}(?:시|군|구)\s+){1,2}"
    r"[가-힣]{1,12}(?:로|길|대로|번길)\s*\d{1,5}(?:-\d{1,5})?"
    r"(?:\s*\([^)]{1,30}\))?"
    r"(?:\s*,?\s*\d{1,4}(?:층|호|동)){0,4}"
)
_ADDRESS_JIBUN_RE = re.compile(
    rf"(?<![가-힣])(?:{_SIDO})(?:특별시|광역시|특별자치시|특별자치도|도|시)?\s+"
    r"(?:[가-힣]{2,10}(?:시|군|구)\s+){1,2}"
    r"[가-힣]{1,10}(?:동|읍|면|리)\s*(?:산\s*)?\d{1,5}(?:-\d{1,5})?(?:\s*번지)?"
    r"(?:\s*,?\s*\d{1,4}(?:층|호|동)){0,4}"
)
_ADDRESS_ROAD_ONLY_RE = re.compile(
    r"(?<![가-힣\d])([가-힣]{2,12}(?:로|길|대로|번길)\s*\d{1,5}(?:-\d{1,5})?"
    r"(?:\s*\d{1,3}(?:층|호))?)"
)
_ADDRESS_DONG_ONLY_RE = re.compile(
    r"(?<![가-힣\d])([가-힣]{2,10}(?:동|읍|면|리)\s*(?:산\s*)?\d{1,5}(?:-\d{1,5})?(?:\s*번지)?"
    r"(?:\s*\d{1,3}(?:층|호))?)"
)
_BUILDING_RE = re.compile(
    r"(?<![가-힣])([가-힣A-Za-z0-9]{2,20}(?:아파트|빌라|오피스텔|빌딩|타워|하이츠|맨션|파크|프라자))"
    r"(?:\s*\d{1,4}동)?(?:\s*\d{1,4}호)?"
)

# 이름: 직책/역할 뒤에 오는 실명
_ROLE = (
    "원고|피고|피고인|피의자|피해자|고소인|고발인|증인|참고인|신청인|상대방|"
    "대표이사|대표|이사|직원|근로자|사용자|계약자|임차인|임대인|매수인|매도인|"
    "채권자|채무자|보증인|상속인|유언자|망인|당사자|담당자|담당|실무자|책임자|"
    "관리자|법정대리인|진술인|목격자|유족|甲|乙|丙|갑|을|병"
)
_NAME_AFTER_ROLE_RE = re.compile(
    rf"(?<![가-힣])(?:{_ROLE})\s*(?:인|측|등)?\s*(?P<name>[가-힣]{{2,4}})"
    rf"(?=[\s,，、()（）\[\]{{}}'\"]|은|는|이|가|을|를|의|에게|께|와|과|도|만|부터|까지|씨|님|측|$)"
)

# 이름: "김민수 씨", "이재훈 님", "김철수 과장"
_NAME_HONORIFIC_RE = re.compile(
    r"(?<![가-힣])(?P<name>[가-힣]{2,4})\s*"
    r"(?:씨|님|과장|부장|차장|대리|팀장|본부장|실장|사장|전무|상무|이사|변호사|법무사|회계사|감정인)(?![가-힣])"
)

# 이름: 역할 표지 뒤의 로마자 이름(John Smith)
_LATIN_NAME_AFTER_ROLE_RE = re.compile(
    rf"(?<![A-Za-z])(?:{_ROLE})\s*[:：]?\s*"
    r"(?P<name>[A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){1,2})"
)

# 회사/법인명
_CORP_RE = re.compile(
    r"(?<![가-힣])((?:\(주\)|㈜)\s*|(?:" + "|".join(COMPANY_FORMS) + r")\s*)"
    r"(?P<name>[가-힣A-Za-z0-9&().\-]{2,30}(?:\s+[가-힣A-Za-z0-9&().\-]{1,15})?)"
)
_CORP_SUFFIX_RE = re.compile(
    r"(?<![가-힣])(?P<name>[가-힣A-Za-z0-9&().\-]{2,30})\s*(?:주식회사|㈜|\(주\)|유한회사)"
)
_CORP_PAREN_RE = re.compile(r"(?<![가-힣])(?P<name>㈜\s?[가-힣A-Za-z0-9&().\-]{2,30})")

# 생년월일(라벨이 있는 경우만)
_BIRTH_RE = re.compile(
    r"(?:생년월일|출생일|출생연월일|생일)\s*[:：]?\s*"
    r"(?P<date>(?:19|20)\d{2}\s*[년.\-/]\s*\d{1,2}\s*[월.\-/]\s*\d{1,2}\s*일?)"
)

# 계좌번호: 은행명 또는 '계좌/입금' 라벨 문맥에서만
_BANK_NAMES = (
    "국민|신한|하나|우리|농협|기업|산업|SC제일|씨티|카카오뱅크|토스뱅크|케이뱅크|"
    "새마을|수협|우체국|부산|대구|광주|전북|경남|제주|한국은행|한국수출입"
)
_ACCOUNT_LABEL_RE = re.compile(
    r"(?:계좌\s*(?:번호)?|입금\s*계좌|송금\s*계좌|예금\s*계좌|계좌번호)\s*[:：]?\s*"
    r"(?P<num>\d[\d\-\s]{7,20}\d)"
)
_ACCOUNT_BANK_RE = re.compile(
    r"(?:" + _BANK_NAMES + r")\s*은행\s*(?:계좌\s*(?:번호)?\s*[:：]?)?\s*"
    r"(?P<num>\d[\d\-]{7,20}\d)"
)


def _rule(
    name: str,
    label: str,
    pattern: re.Pattern,
    *,
    group: int = 0,
    validator=None,
    post_filter=None,
    trim=None,
    priority: int = 100,
) -> Rule:
    return Rule(name, label, pattern, group, validator, post_filter, trim, priority)


RULES: List[Rule] = [
    # --- 고유식별번호 (우선순위 높음: 서로 겹치는 패턴보다 먼저)
    # 6-7 형식은 생년월일이 성립하면 주민등록번호로 본다(OCR 오독으로 검증번호가
    # 틀려도 놓치지 않도록 검증번호는 '확신' 신호로만 쓴다).
    _rule(
        "rrn", "RRN", _RRN_RE, priority=200,
        validator=is_plausible_rrn,
    ),
    _rule(
        "corp_no", "CORPNO", _RRN_RE, priority=190,
        validator=is_valid_corp_no,
    ),
    _rule("biz_no", "BIZNO", _BIZ_RE, priority=180),
    _rule("license", "LICENSE", _LICENSE_RE, priority=170, validator=None),
    _rule("passport", "PASSPORT", _PASSPORT_RE, priority=170),
    _rule("card", "CARD", _CARD_RE, priority=160, post_filter=_card_ok),
    # --- 연락처
    _rule("mobile", "PHONE", _MOBILE_RE, priority=150),
    _rule("landline", "PHONE", _LANDLINE_RE, priority=140),
    _rule("email", "EMAIL", _EMAIL_RE, priority=150),
    _rule("vehicle", "VEHICLE", _VEHICLE_RE, priority=140),
    _rule("ip", "IP", _IP_RE, priority=60),
    # --- 계좌
    _rule("account_label", "ACCOUNT", _ACCOUNT_LABEL_RE, group=1, priority=130),
    _rule("account_bank", "ACCOUNT", _ACCOUNT_BANK_RE, group=1, priority=130),
    # --- 주소
    _rule("address_full", "ADDRESS", _ADDRESS_FULL_RE, priority=125, post_filter=_address_ok),
    _rule("address_jibun", "ADDRESS", _ADDRESS_JIBUN_RE, priority=124, post_filter=_address_ok),
    _rule("building", "ADDRESS", _BUILDING_RE, priority=70, post_filter=_address_ok),
    _rule("address_road", "ADDRESS", _ADDRESS_ROAD_ONLY_RE, group=1, priority=65, post_filter=_address_ok),
    _rule("address_dong", "ADDRESS", _ADDRESS_DONG_ONLY_RE, group=1, priority=64, post_filter=_address_ok),
    # --- 이름
    _rule(
        "name_role", "PERSON", _NAME_AFTER_ROLE_RE, group=1, priority=120,
        post_filter=_name_ok,
    ),
    _rule("name_honorific", "PERSON", _NAME_HONORIFIC_RE, group=1, priority=115, post_filter=_name_ok),
    _rule("name_latin", "PERSON", _LATIN_NAME_AFTER_ROLE_RE, group=1, priority=114),
    # --- 회사/법인
    _rule("corp_form", "ORG", _CORP_RE, group=0, priority=110, post_filter=_corp_name_ok, trim=trim_corp),
    _rule(
        "corp_suffix", "ORG", _CORP_SUFFIX_RE, group=1, priority=109,
        post_filter=_corp_name_ok, trim=trim_particle,
    ),
    _rule("corp_paren", "ORG", _CORP_PAREN_RE, group=1, priority=108, post_filter=_corp_name_ok),
    # --- 생년월일
    _rule("birth", "BIRTH", _BIRTH_RE, group=1, priority=100),
]


# --------------------------------------------------------------------------
# 탐색/판정
# --------------------------------------------------------------------------


def find_matches(text: str, rules: Optional[Iterable[Rule]] = None) -> List[Match]:
    """모든 정형 패턴 일치를 찾아 반환(겹침 해소 전)."""
    matches: List[Match] = []
    for rule in rules or RULES:
        for m in rule.pattern.finditer(text):
            try:
                start, end = m.span(rule.group)
            except IndexError:
                continue
            if start < 0 or end <= start:
                continue
            value = text[start:end]
            if rule.validator and not rule.validator(value):
                continue
            if rule.post_filter and not rule.post_filter(value, text, start, end):
                continue
            if rule.trim:
                trimmed = rule.trim(value)
                if trimmed and value.startswith(trimmed):
                    end = start + len(trimmed)
                    value = trimmed
                    if len(value) < 2:
                        continue
                    if rule.validator and not rule.validator(value):
                        continue
                    if rule.post_filter and not rule.post_filter(value, text, start, end):
                        continue
            matches.append(Match(start, end, value, rule.label, rule.name, rule.priority))
    return matches


def resolve_overlaps(matches: List[Match]) -> List[Match]:
    """겹치는 일치 중 우선순위·길이가 큰 것을 남긴다."""
    ordered = sorted(matches, key=lambda m: (-m.priority, -(m.end - m.start), m.start))
    chosen: List[Match] = []
    for cand in ordered:
        overlaps = False
        for kept in chosen:
            if cand.start < kept.end and kept.start < cand.end:
                overlaps = True
                break
        if not overlaps:
            chosen.append(cand)
    return sorted(chosen, key=lambda m: m.start)


def is_kept_entity(value: str) -> bool:
    """비식별화하면 안 되는 개체(법원·법령·판례·재판부 등)인지 판정."""
    text = value.strip()
    if not text:
        return True
    if not re.search(r"[가-힣A-Za-z]", text):
        return True
    if KEEP_INSTITUTION_RE.search(text):
        return True
    if COURT_DIVISION_RE.search(text):
        return True
    if LAW_WORD_RE.search(text):
        return True
    if CASE_NO_RE.search(text):
        return True
    if re.fullmatch(r"(?:19|20)\d{2}\s*[년.\-/]\s*\d{1,2}\s*[월.\-/]\s*\d{1,2}\s*일?", text):
        return True
    return False


def is_valid_person_name(value: str) -> bool:
    name = value.strip()
    if not (2 <= len(name) <= 4):
        return False
    if not re.fullmatch(r"[가-힣]{1,2}\s?[가-힣]{1,3}", name):
        return False
    compact = name.replace(" ", "")
    if compact in NAME_STOPWORDS:
        return False
    if compact.endswith(("법", "원", "청", "부", "처", "국", "회", "단", "팀", "실", "소", "관")):
        return False
    return compact[:2] in COMPOUND_SURNAMES or compact[0] in SURNAMES


def is_valid_org_name(value: str) -> bool:
    name = value.strip()
    if not (2 <= len(name) <= 60):
        return False
    if name in GENERIC_ORG_STOPWORDS:
        return False
    if is_kept_entity(name):
        return False
    return True


def is_valid_address(value: str) -> bool:
    return _address_ok(value)
