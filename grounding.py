"""근거 가드 — 리포트의 사실 주장이 실제 API 응답에 있는지 검사한다.

MateAI(캐릭터챗 엔진)의 `mateai/grounding.py` 메커니즘을 여행 도메인으로 옮긴 것이다.
**메커니즘은 그대로, 검사 대상만 도메인에 맞게 바꿨다.**

  MateAI   : 시각·열차번호·요금·승강장  ← 기관 API가 준 값
  여기      : 가게 이름·주소            ← 지도 API가 준 값

왜 필요한가
    과제는 "실제 날씨/행사 데이터의 정확도를 평가하는 미션이 아니다"라고 명시한다.
    그래서 대부분의 구현은 LLM이 지어낸 것을 그대로 리포트에 싣는다.
    그런데 **맛집은 다르다.** 지도 API가 실제 데이터를 주는데도 LLM이 최종 리포트를
    쓰면서 없는 가게를 만들어 낼 수 있다. 그 문장은 검증 가능하므로 검사한다.

무엇을 검사하지 않는가
    날씨·행사는 LLM 추정이다. 검증할 근거가 없으므로 **검사하지 않는 대신
    리포트에 '추정'이라고 표시**한다. 검사할 수 없는 것을 검사한 척하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Verdict(Enum):
    PASS = "pass"           # 검사 대상이 있었고 전부 근거에 있다
    NO_CLAIM = "no_claim"   # 검사할 사실 주장이 없다 (감점하지 않는다)
    REFUSE = "refuse"       # 근거 없는 주장이 있다


@dataclass
class Claim:
    value: str        # 리포트에 등장한 가게 이름
    sentence: str     # 그 이름이 있던 줄
    supported: bool = False


@dataclass
class Report:
    verdict: Verdict
    claims: list[Claim] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def unsupported(self) -> list[Claim]:
        return [c for c in self.claims if not c.supported]

    @property
    def score(self) -> float:
        """[0,1]. 주장이 없으면 1.0 — 말을 아낀 것을 감점하지 않는다."""
        if not self.claims:
            return 1.0
        return sum(c.supported for c in self.claims) / len(self.claims)


def _normalise(value: str) -> str:
    """공백·구두점을 지우고 대문자로. '샤브20 만촌점' == '샤브20만촌점'."""
    return re.sub(r"[\s,\-·()\[\]'\"]", "", value).upper()


# 마크다운 목록 줄에서 가게 이름처럼 보이는 부분을 뽑는다.
#   - **가게이름** — 주소       → 가게이름
#   - 가게이름 (주소)           → 가게이름
#   1. 가게이름 · 카테고리       → 가게이름
_LIST_LINE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.+)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def extract_place_claims(markdown: str, section_hint: str = "맛집") -> list[Claim]:
    """리포트의 맛집 섹션에서 가게 이름을 뽑는다.

    섹션을 좁히는 이유: 일정 제안이나 추천 이유에 지역명·일반명사가 섞이는데,
    그것까지 '가게 이름'으로 잡으면 멀쩡한 문장이 잘린다.
    검사는 **좁게, 확실한 것만** 한다 — MateAI에서 감정 표현을 검사 대상에서
    뺀 것과 같은 판단이다.
    """
    claims: list[Claim] = []
    section_level = 0          # 0이면 섹션 밖. 1 이상이면 그 레벨의 맛집 섹션 안.

    for raw in markdown.splitlines():
        line = raw.rstrip()

        m_head = _HEADING.match(line)
        if m_head:
            level = len(m_head.group(1))
            if section_hint in m_head.group(2):
                section_level = level          # 맛집 섹션에 들어간다
            elif section_level and level <= section_level:
                section_level = 0              # 같거나 상위 레벨 헤딩 = 섹션 종료
            # 하위 레벨 헤딩(### 경주)은 섹션 안의 소제목이므로 상태를 유지한다
            continue
        if not section_level:
            continue

        m = _LIST_LINE.match(line)
        if not m:
            continue
        body = m.group(1).strip()
        if not body or body.startswith("데이터 없음"):
            continue

        # **굵게** 표시가 있으면 그것이 이름이다. 없으면 첫 구분자 앞까지.
        bold = _BOLD.search(body)
        name = bold.group(1) if bold else re.split(r"\s+[—–·|(]|\s{2,}", body)[0]
        name = name.strip().strip("*_`")
        if name:
            claims.append(Claim(value=name, sentence=line.strip()))
    return claims


def check(markdown: str, places: list[dict], sources: list[str]) -> Report:
    """맛집 섹션의 가게 이름이 전부 지도 API 응답에 있는지 검사한다."""
    index = {_normalise(p.get("name", "")) for p in places if p.get("name")}
    claims = extract_place_claims(markdown)
    for c in claims:
        c.supported = _normalise(c.value) in index

    if not claims:
        verdict = Verdict.NO_CLAIM
    elif all(c.supported for c in claims):
        verdict = Verdict.PASS
    else:
        verdict = Verdict.REFUSE
    return Report(verdict=verdict, claims=claims, sources=sorted(set(sources)))


def annotate(markdown: str, report: Report) -> str:
    """근거 없는 가게 이름이 있는 줄에 표시를 붙인다.

    MateAI는 문장을 **제거**했지만 여기서는 **표시만** 한다.
    리포트는 사람이 읽고 판단하는 문서이고, 지워 버리면 무엇이 문제였는지
    독자가 알 수 없기 때문이다. 대신 어떤 줄이 왜 걸렸는지 남긴다.
    """
    if not report.unsupported:
        return markdown

    bad = {c.sentence: c.value for c in report.unsupported}
    out = []
    for raw in markdown.splitlines():
        stripped = raw.strip()
        if stripped in bad:
            out.append(f"{raw}  <!-- ⚠️ 근거 없음: '{bad[stripped]}' 은(는) 검색 결과에 없습니다 -->")
        else:
            out.append(raw)
    return "\n".join(out)
