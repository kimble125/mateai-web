"""근거 검증기 — cite-or-refuse.

기획서 §4-4의 "근거 없는 문장 금지"를 **실행 가능한 검사기**로 만든 것.
기획서에는 "자동 검사"라고만 적혀 있었고 구현체가 없었다. 이 모듈이 그 구현이다.

두 가지 역할을 겸한다.
  1) 런타임 가드: 응답을 내보내기 전에 미지원 주장을 차단한다.
  2) 평가 지표: 5축 루브릭의 Groundedness를 **사람 없이** 계산한다.
     -> evalkit/rubric.py 가 이 모듈을 그대로 재사용한다.

왜 이게 이 프로젝트의 핵심인가:
  관계형 챗봇에서 오류는 기능 실패가 아니라 '정을 쌓은 친구의 배신'으로 체감된다.
  따라서 몰입을 포기하는 대신, 사실 주장만 좁게 잡아내 차단한다.
  캐릭터의 감정·의견·권유는 검사 대상이 아니다 -- 그게 레이어 분리의 요점이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

# ── 사실 주장 패턴 ────────────────────────────────────────────────────────
# 좁게 잡는다. 넓게 잡으면 캐릭터가 말을 못 하게 되고, 레이어 분리가 무의미해진다.
CLAIM_PATTERNS: dict[str, re.Pattern] = {
    "time": re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b"),
    # 두 번째 그룹에 숫자를 강제한다 -- 없으면 "KTX KTX" 같은 문자열이 열차번호로 잡힌다.
    "train_no": re.compile(r"\b(KTX|ITX|SRT|Mugunghwa)[- ]?([A-Za-z0-9]*\d[A-Za-z0-9]*)\b", re.I),
    "flight_no": re.compile(r"\b([A-Z]{2}\d{2,4})\b"),
    "duration": re.compile(r"\b(\d{1,3})\s?(?:min|mins|minutes|hours?|hrs?|분|시간)\b", re.I),
    "price": re.compile(r"(?:₩|KRW|\$)\s?([\d,]+)"),
    "platform": re.compile(r"\bplatform\s+(\d{1,2})\b", re.I),
    "count": re.compile(r"\b(\d{1,4})\s?(?:people|passengers|명|대)\b", re.I),
}

# 캐릭터가 자유롭게 말해도 되는 것: 감정, 의견, 권유, 질문.
# 이 표지가 붙은 문장은 사실 검사를 면제한다(hedge = 단정하지 않음).
HEDGES = (
    "i think", "maybe", "probably", "i'd say", "if you like", "i love",
    "my favourite", "my favorite", "i remember", "feels like", "i guess",
)


class Verdict(str, Enum):
    PASS = "pass"           # 모든 주장이 근거에 있음
    REFUSE = "refuse"       # 미지원 주장 있음 -> 발화 차단
    NO_CLAIM = "no_claim"   # 검사할 사실 주장이 없음 (캐릭터 발화)


@dataclass(frozen=True)
class Claim:
    kind: str
    value: str
    sentence: str
    supported: bool = False


@dataclass
class GroundingReport:
    verdict: Verdict
    claims: list[Claim] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)

    @property
    def unsupported(self) -> list[Claim]:
        return [c for c in self.claims if not c.supported]

    @property
    def score(self) -> float:
        """Groundedness [0,1]. 주장이 없으면 1.0 (감점하지 않는다)."""
        if not self.claims:
            return 1.0
        return sum(c.supported for c in self.claims) / len(self.claims)

    def refusal_text(self) -> str:
        kinds = sorted({c.kind for c in self.unsupported})
        return (
            "I can't confirm that ("
            + ", ".join(kinds)
            + "). Please check the official channel — I won't guess."
        )


def _normalise(v: str) -> str:
    return re.sub(r"[\s,\-]", "", v).upper()


def evidence_index(evidence: list[dict]) -> set[str]:
    """API 응답·RAG 청크에서 대조 가능한 값 집합을 만든다."""
    return set(evidence_roles(evidence))


def evidence_roles(evidence: list[dict]) -> dict[str, set[str]]:
    """값 → 그 값이 근거에서 맡은 **역할(필드명)** 집합.

    값만 모아 두면 "22:15에 출발한다"처럼 **도착 시각을 출발로 바꿔 말한 문장**을
    통과시킨다 — 숫자 자체는 근거에 있기 때문이다. 실제로 LLM을 물려 돌려 보다가
    이 구멍을 발견했다. 역할까지 들고 있어야 이런 뒤바뀜을 잡을 수 있다.
    """
    roles: dict[str, set[str]] = {}

    def add(value: str, role: str) -> None:
        roles.setdefault(_normalise(value), set()).add(role)

    for item in evidence:
        for key, value in item.items():
            if value is None:
                continue
            text = str(value)
            add(text, key)
            for pat in CLAIM_PATTERNS.values():
                for m in pat.finditer(text):
                    add(m.group(0), key)
    return roles


def extract_claims(text: str) -> list[Claim]:
    claims: list[Claim] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        if not sentence.strip():
            continue
        if any(h in sentence.lower() for h in HEDGES):
            continue  # 캐릭터의 주관 표현 — 사실 검사 면제
        for kind, pat in CLAIM_PATTERNS.items():
            for m in pat.finditer(sentence):
                claims.append(Claim(kind=kind, value=m.group(0), sentence=sentence.strip()))
    return claims


# 문장이 시각의 '역할'을 지목하는 단서. 이게 있으면 값이 그 역할이어야 한다.
ROLE_CUES: dict[str, tuple[str, ...]] = {
    "dep": ("depart", "departs", "departing", "leave", "leaves", "leaving", "boarding"),
    "arr": ("arrive", "arrives", "arriving", "gets in", "get in", "lands"),
}


def _role_cue(sentence: str, value: str) -> str | None:
    """값 **바로 앞**의 역할 단서를 찾는다.

    문장 단위로 보면 "Take KTX-169 at 20:30, arriving 22:15."에서 'arriving'이
    20:30까지 지배해 버린다. 한 문장에 출발과 도착이 같이 오는 것이 정상이므로,
    각 값에 대해 그 앞쪽 구간에서 가장 가까운 단서만 본다.
    """
    low = sentence.lower()
    at = low.find(value.lower())
    before = low[:at] if at >= 0 else low
    best_role, best_pos = None, -1
    for role, cues in ROLE_CUES.items():
        for c in cues:
            pos = before.rfind(c)
            if pos > best_pos:
                best_role, best_pos = role, pos
    return best_role


def _supported(claim: Claim, roles: dict[str, set[str]]) -> bool:
    got = roles.get(_normalise(claim.value))
    if got is None:
        return False
    if claim.kind != "time":
        return True
    cue = _role_cue(claim.sentence, claim.value)
    # 역할 단서가 없으면 지금처럼 값만 본다. 있으면 역할까지 맞아야 한다.
    return cue is None or cue in got


def check(text: str, evidence: list[dict]) -> GroundingReport:
    """응답 텍스트의 모든 사실 주장이 근거에 있는지 검사한다."""
    roles = evidence_roles(evidence)
    claims = [
        Claim(c.kind, c.value, c.sentence, supported=_supported(c, roles))
        for c in extract_claims(text)
    ]
    citations = sorted({str(e["source"]) for e in evidence if e.get("source")})
    if not claims:
        verdict = Verdict.NO_CLAIM
    elif all(c.supported for c in claims):
        verdict = Verdict.PASS
    else:
        verdict = Verdict.REFUSE
    return GroundingReport(verdict=verdict, claims=claims, citations=citations)


def guard(text: str, evidence: list[dict], *, mode: str = "guide") -> tuple[str, GroundingReport]:
    """발화 직전 가드. 위반 시 가이드 모드는 차단, 컴패니언은 해당 문장만 제거한다.

    모드별로 다르게 처리하는 이유: 가이드 모드에서 틀린 시각 하나는 여정을 망치지만,
    컴패니언 모드에서 문장 하나를 잃는 것은 대화를 망치지 않는다.
    """
    report = check(text, evidence)
    if report.verdict is not Verdict.REFUSE:
        return text, report
    if mode == "guide":
        return report.refusal_text(), report
    bad = {c.sentence for c in report.unsupported}
    kept = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip() and s.strip() not in bad]
    return (" ".join(kept) or report.refusal_text()), report
