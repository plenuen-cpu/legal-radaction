"""2단계 비식별화 엔진.

1단계: 정형 패턴(주민등록번호·전화·계좌·카드·주소 등)을 결정적으로 치환.
2단계: 로컬 LLM이 문맥에서 사람 이름·주소·회사/기관명을 찾아 치환.
        법원·재판부·법령·판례번호는 후처리 가드로 제외한다.

같은 개체는 문서 전체에서 같은 번호([이름1], [주소1] …)로 매핑된다.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

import patterns as P

LABEL_NAMES = {
    "PERSON": "이름",
    "ADDRESS": "주소",
    "ORG": "회사",
    "RRN": "주민번호",
    "CORPNO": "법인번호",
    "BIZNO": "사업자번호",
    "PHONE": "전화",
    "EMAIL": "이메일",
    "ACCOUNT": "계좌",
    "CARD": "카드",
    "VEHICLE": "차량",
    "PASSPORT": "여권",
    "LICENSE": "면허",
    "BIRTH": "생년월일",
    "IP": "IP",
    "OTHER": "기타",
}

LLM_TYPE_TO_LABEL = {
    "PERSON": "PERSON",
    "NAME": "PERSON",
    "PER": "PERSON",
    "ADDRESS": "ADDRESS",
    "ADDR": "ADDRESS",
    "LOC": "ADDRESS",
    "ORG": "ORG",
    "ORGANIZATION": "ORG",
    "COMPANY": "ORG",
}

# 이름 뒤에 붙는 조사(문서 전체 빈도로 이름 경계를 보정할 때 사용)
NAME_PARTICLES = (
    "에게서", "으로부터", "에서는", "이라고", "에게", "께서", "부터", "까지",
    "에서", "으로", "은", "는", "이", "가", "을", "를", "의", "에", "와", "과",
    "도", "만", "로", "께", "측",
)

LATIN_NAME_RE = re.compile(r"^[A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){1,2}$")


def normalize_key(value: str) -> str:
    key = re.sub(r"\s+", "", value or "").strip()
    key = key.strip(".,;:()[]{}\"'")
    if key.isascii():
        key = key.lower()
    return key


@dataclass
class MappingEntry:
    index: int
    label: str
    placeholder: str
    original: str
    count: int = 0
    sources: set = field(default_factory=set)

    @property
    def type_name(self) -> str:
        return LABEL_NAMES.get(self.label, self.label)


class MappingTable:
    """원문 ↔ 치환표 관리. 같은 개체는 항상 같은 표기를 받는다."""

    def __init__(self, style: str = "pseudonym", mask_text: str = "***"):
        self.style = style
        self.mask_text = mask_text
        self.entries: List[MappingEntry] = []
        self._by_key: Dict[str, MappingEntry] = {}
        self._counters: Counter = Counter()

    def placeholder_for(self, original: str, label: str, source: str = "regex") -> str:
        key = normalize_key(original)
        if not key:
            return original
        entry = self._by_key.get(key + "\u0000" + label)
        if entry is None:
            if self.style == "mask":
                placeholder = self.mask_text or "***"
            else:
                self._counters[label] += 1
                placeholder = f"[{LABEL_NAMES.get(label, '기타')}{self._counters[label]}]"
            entry = MappingEntry(
                index=len(self.entries) + 1,
                label=label,
                placeholder=placeholder,
                original=original,
                count=0,
            )
            self.entries.append(entry)
            self._by_key[key + "\u0000" + label] = entry
        entry.count += 1
        if source:
            entry.sources.add(source)
        return entry.placeholder

    def lookup(self, original: str, label: str) -> Optional[MappingEntry]:
        return self._by_key.get(normalize_key(original) + "\u0000" + label)

    def rows(self) -> List[dict]:
        return [
            {
                "번호": e.index,
                "유형": e.type_name,
                "원문": e.original,
                "대체표시": e.placeholder,
                "등장횟수": e.count,
            }
            for e in self.entries
        ]

    def __len__(self) -> int:
        return len(self.entries)


@dataclass
class DeidResult:
    text: str
    table: MappingTable
    stats: Counter
    warnings: List[str] = field(default_factory=list)
    llm_used: bool = False
    llm_chunks: int = 0


# --------------------------------------------------------------------------
# 문서 단위 이름 경계 보정
# --------------------------------------------------------------------------


def _count_name_occurrences(text: str, word: str, allow_particle: bool = False) -> int:
    if allow_particle:
        tail = "|".join(NAME_PARTICLES)
        pattern = re.escape(word) + rf"(?=(?:{tail})|[\s,.;:()\[\]]|$)"
    else:
        pattern = re.escape(word) + r"(?![가-힣])"
    return len(re.findall(pattern, text))


def refine_person_match(match: P.Match, full_text: str) -> P.Match:
    """'이재훈은'처럼 조사가 함께 잡힌 이름을 문서 전체 빈도로 보정한다.

    같은 문서에서 '이재훈'이 여러 번(조사가 붙은 형태 포함) 나오면 조사를 떼고,
    '김정은'처럼 이름 자체가 조사 글자로 끝나는 경우에는 그대로 둔다.
    """
    value = match.text
    if len(value) < 3 or not re.fullmatch(r"[가-힣]+", value):
        return match
    full_count = _count_name_occurrences(full_text, value)
    for particle in NAME_PARTICLES:
        if not value.endswith(particle):
            continue
        stem = value[: -len(particle)]
        if len(stem) < 2 or not P.is_valid_person_name(stem):
            continue
        stem_count = _count_name_occurrences(full_text, stem, allow_particle=True)
        if stem_count > full_count or (stem_count == full_count and len(value) == 4):
            return P.Match(
                match.start, match.start + len(stem), stem, match.label,
                match.rule, match.priority,
            )
    return match


# --------------------------------------------------------------------------
# LLM 결과 가드
# --------------------------------------------------------------------------


def _valid_llm_entity(text: str, label: str) -> bool:
    value = text.strip()
    if not value or len(value) < 2 or len(value) > 80:
        return False
    if P.PLACEHOLDER_RE.search(value):
        return False
    if P.is_kept_entity(value):
        return False
    if label == "PERSON":
        return P.is_valid_person_name(value) or bool(LATIN_NAME_RE.match(value))
    if label == "ADDRESS":
        return P.is_valid_address(value)
    if label == "ORG":
        return P.is_valid_org_name(value)
    return False


def _merge_adjacent_addresses(text: str, spans: List[P.Match]) -> List[P.Match]:
    """'정자동 123-4' + '래미안아파트 101동 1002호'처럼 붙어 있는 주소를 하나로 묶는다."""
    merged: List[P.Match] = []
    for span in sorted(spans, key=lambda m: m.start):
        if merged and span.label == "ADDRESS" and merged[-1].label == "ADDRESS":
            prev = merged[-1]
            gap = text[prev.end:span.start]
            if len(gap) <= 5 and gap.strip(" ,\t") == "":
                merged[-1] = P.Match(
                    prev.start, span.end, text[prev.start:span.end],
                    "ADDRESS", prev.rule, prev.priority,
                )
                continue
        merged.append(span)
    return merged


def _apply_spans(text: str, spans: Sequence[P.Match], table: MappingTable,
                 source: str = "regex") -> tuple:
    """겹치지 않는 구간을 치환해 (결과문자열, 사용된 구간) 반환."""
    if not spans:
        return text, []
    ordered = sorted(spans, key=lambda m: (m.start, -(m.end - m.start)))
    pieces: List[str] = []
    used: List[P.Match] = []
    cursor = 0
    for span in ordered:
        if span.start < cursor:
            continue
        if span.end <= span.start:
            continue
        value = text[span.start:span.end]
        if source == "llm":
            # LLM이 준 문자열이 실제 구간과 일치하는지 재확인
            if value != span.text:
                continue
        placeholder = table.placeholder_for(value, span.label, source)
        pieces.append(text[cursor:span.start])
        pieces.append(placeholder)
        cursor = span.end
        used.append(span)
    pieces.append(text[cursor:])
    return "".join(pieces), used


# --------------------------------------------------------------------------
# 청킹
# --------------------------------------------------------------------------

_SENTENCE_END_RE = re.compile(r"(?<=[.!?。？！])\s|\n\n")

_PARTICLE_TAIL = "|".join(NAME_PARTICLES) + "|씨|님|측|등|들"


def find_occurrences(text: str, value: str) -> List[int]:
    """한 번 확인된 이름·회사명의 문서 전체 등장 위치를 찾는다."""
    pattern = re.compile(
        r"(?<![가-힣A-Za-z0-9])" + re.escape(value) + rf"(?=(?:{_PARTICLE_TAIL})|[^가-힣]|$)"
    )
    return [m.start() for m in pattern.finditer(text)]


def split_chunks(text: str, size: int = 1200) -> List[str]:
    """문단·문장 경계를 존중하며 size자 내외로 나눈다."""
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: List[str] = []
    buffer = ""
    for block in re.split(r"(\n\n+)", text):
        if not block:
            continue
        if len(buffer) + len(block) <= size:
            buffer += block
            continue
        if buffer:
            chunks.append(buffer)
            buffer = ""
        if len(block) <= size:
            buffer = block
            continue
        # 한 문단이 너무 길면 문장 단위로 자른다
        sentence = ""
        for part in re.split(r"(?<=[.!?。？！])\s+", block):
            if len(sentence) + len(part) + 1 <= size:
                sentence += (" " if sentence else "") + part
            else:
                if sentence:
                    chunks.append(sentence)
                while len(part) > size:
                    chunks.append(part[:size])
                    part = part[size:]
                sentence = part
        if sentence:
            buffer = sentence
    if buffer:
        chunks.append(buffer)
    return [c for c in chunks if c.strip()]


# --------------------------------------------------------------------------
# 본 엔진
# --------------------------------------------------------------------------


class Deidentifier:
    def __init__(
        self,
        style: str = "pseudonym",
        mask_text: str = "***",
        llm=None,
        chunk_size: int = 1200,
        use_llm: bool = True,
        progress: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ):
        self.style = style
        self.mask_text = mask_text
        self.llm = llm
        self.chunk_size = chunk_size
        self.use_llm = use_llm
        self.progress = progress or (lambda message: None)
        self.cancel_check = cancel_check or (lambda: False)

    # -- 1단계 ---------------------------------------------------------
    def _regex_stage(self, text: str, table: MappingTable):
        matches = P.resolve_overlaps(P.find_matches(text))
        refined = []
        for match in matches:
            if match.label == "PERSON":
                match = refine_person_match(match, text)
            refined.append(match)
        refined = P.resolve_overlaps(refined)

        # 한 번이라도 확인된 이름·회사명은 문서 전체에서 같은 표기로 바꾼다.
        expanded: List[P.Match] = list(refined)
        seen = set()
        for match in refined:
            if match.label not in ("PERSON", "ORG"):
                continue
            value = match.text
            if not (2 <= len(value) <= 40):
                continue
            key = (match.label, normalize_key(value))
            if key in seen:
                continue
            seen.add(key)
            for start in find_occurrences(text, value):
                if start == match.start:
                    continue
                expanded.append(
                    P.Match(start, start + len(value), value, match.label, match.rule + "_global", match.priority)
                )
        if len(expanded) > len(refined):
            refined = P.resolve_overlaps(expanded)

        refined = _merge_adjacent_addresses(text, refined)

        masked, used = _apply_spans(text, refined, table, source="regex")
        return masked, used

    # -- 2단계 ---------------------------------------------------------
    def _llm_stage(self, text: str, table: MappingTable):
        spans: List[P.Match] = []
        warnings: List[str] = []
        chunks = split_chunks(text, self.chunk_size)
        seen_chunks = set()
        used_chunks = 0
        for idx, chunk in enumerate(chunks, start=1):
            if self.cancel_check():
                break
            if not chunk.strip() or not re.search(r"[가-힣]", chunk):
                continue
            signature = hash(chunk)
            if signature in seen_chunks:
                continue
            seen_chunks.add(signature)
            self.progress(f"AI 분석 {idx}/{len(chunks)}")
            try:
                entities = self.llm.extract_entities(chunk)
            except Exception as exc:  # LLM 오류는 전체 작업을 막지 않는다
                warnings.append(f"AI 분석 실패(구간 {idx}): {exc}")
                continue
            used_chunks += 1
            for entity in entities or []:
                if not isinstance(entity, dict):
                    continue
                label = LLM_TYPE_TO_LABEL.get(str(entity.get("type", "")).upper())
                value = str(entity.get("text", "")).strip()
                if not label or not value:
                    continue
                if not _valid_llm_entity(value, label):
                    continue
                for found in re.finditer(re.escape(value), text):
                    start, end = found.span()
                    if start > 0 and re.match(r"[가-힣]", text[start - 1]) and re.match(r"[가-힣]", value[0]):
                        # 단어 중간에서 시작하는 우연한 일치는 제외
                        continue
                    spans.append(P.Match(start, end, value, label, "llm", 90))
        return spans, used_chunks, warnings

    # -- 전체 ----------------------------------------------------------
    def process(self, text: str) -> DeidResult:
        table = MappingTable(self.style, self.mask_text)
        stats: Counter = Counter()
        warnings: List[str] = []

        masked, used = self._regex_stage(text, table)
        for match in used:
            stats[match.label] += 1
        if used:
            self.progress(f"정형 패턴 {len(used)}건 치환")

        llm_used = False
        llm_chunks = 0
        if self.use_llm and self.llm is not None:
            self.progress("AI 문맥 분석 준비")
            spans, llm_chunks, llm_warnings = self._llm_stage(masked, table)
            warnings.extend(llm_warnings)
            if spans:
                # 겹치는 LLM 구간 정리 후 적용
                spans = self._dedupe(spans)
                masked, used_llm = _apply_spans(masked, spans, table, source="llm")
                for match in used_llm:
                    stats[match.label] += 1
                llm_used = bool(used_llm)
            if llm_chunks:
                warnings.append(f"AI 문맥 분석 {llm_chunks}개 구간 완료")
        elif self.use_llm and self.llm is None:
            warnings.append("AI 모델이 없어 정형 패턴만 적용했습니다. 이름·주소 일부가 남을 수 있습니다.")
        else:
            warnings.append("AI 문맥 분석을 사용하지 않았습니다. 이름·주소 일부가 남을 수 있습니다.")

        return DeidResult(
            text=masked,
            table=table,
            stats=stats,
            warnings=warnings,
            llm_used=llm_used,
            llm_chunks=llm_chunks,
        )

    @staticmethod
    def _dedupe(spans: List[P.Match]) -> List[P.Match]:
        seen = set()
        unique = []
        for span in spans:
            key = (span.start, span.end, span.label)
            if key in seen:
                continue
            seen.add(key)
            unique.append(span)
        # 같은 구간에 여러 라벨이 있으면 PERSON > ADDRESS > ORG 순
        unique.sort(key=lambda m: (m.start, -(m.end - m.start), m.label))
        result: List[P.Match] = []
        cursor = -1
        for span in unique:
            if span.start < cursor:
                continue
            result.append(span)
            cursor = span.end
        return result
