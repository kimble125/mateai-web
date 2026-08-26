"""엔드투엔드 응답 파이프라인 — 여섯 레이어를 한 번의 턴으로 엮는다.

    입력(사용자 발화 + 여정 상태)
      -> 라우터        모드와 발화량 결정          (router.py)
      -> 규칙 엔진      실행 가능 후보 산출          (feasibility.py)
      -> 캐릭터 레이어   프롬프트 조립               (persona.py)
      -> 생성          [가이드=결정론 / 컴패니언=LLM]
      -> 근거 가드      cite-or-refuse             (grounding.py)
      -> 신호 로깅      학습 데이터의 원천           (signals.py)

가이드 모드에 LLM을 연결하지 않는 것이 이 파이프라인의 핵심이다.
`generate` 훅은 컴패니언 모드에서만 호출된다 -- 구조적으로 환각이 운행 정보로 새지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from feasibility import Candidate, derived_evidence, min_to_hhmm, plan_options, ready_window
from grounding import GroundingReport, guard
from journey import JourneyCard
from persona import MINTAE, CharacterCard, MemoryCard, consistency
from router import COMPANION, GUIDE, RouteDecision, route
from signals import Event, SignalEvent, SignalLog

Generator = Callable[[str, int], str]  # (system_prompt, max_tokens) -> text


_ALPHA_HEAD = re.compile(r"[A-Za-z]+")


def train_label(t: dict) -> str:
    """'ITX-새마을 ITX-1045'처럼 종류가 두 번 나오지 않게 한다.

    열차번호가 이미 종류를 접두로 달고 있으면(KTX-153, ITX-1045) 번호만 쓴다.
    kind는 한글 이름을 포함할 수 있으므로(ITX-새마을) 전체 문자열이 아니라
    **앞쪽 영문 토큰끼리** 비교해야 한다 — 이 비교를 문자열 전체로 하면
    "ITX-1045".startswith("ITX-새마을")이 False가 되어 종류가 중복 출력된다.
    """
    no, kind = str(t["no"]), str(t["kind"])
    a, b = _ALPHA_HEAD.match(no), _ALPHA_HEAD.match(kind)
    if a and b and a.group().upper() == b.group().upper():
        return no
    return f"{kind} {no}"


@dataclass
class Turn:
    mode: str
    text: str
    decision: RouteDecision
    grounding: GroundingReport | None = None
    options: list[Candidate] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    persona_score: float = 1.0


def guide_text(flight: dict, options: list[Candidate], rejected: list[Candidate],
               source: dict, character: CharacterCard = MINTAE) -> tuple[str, list[dict]]:
    """가이드 모드 응답은 **템플릿**이다. LLM이 관여하지 않는다.

    다만 템플릿의 문안은 캐릭터의 목소리다(`CharacterCard.guide_lines`).
    사람이 미리 쓴 문장이므로 결정론이고, 동시에 위기 상황에서 캐릭터가 사라지지 않는다.
    """
    g = character.guide_lines
    window = ready_window(flight)
    lines = [
        g["flight"].format(flight_no=flight["flight_no"], status=flight["status"],
                           time=flight.get("estimated") or flight["scheduled"]),
        g["ready"].format(ready=min_to_hhmm(window.hi)),
    ]
    # API 근거 + 규칙 엔진이 계산한 파생 근거. 후자가 없으면 가드가 자기 답변을 막는다.
    evidence = [dict(flight, source=source.get("flight_source", "airport API"))]
    evidence += derived_evidence(flight, options + rejected[:1])

    if not options:
        lines.append(g["none"])
    else:
        lines.append(g["options"])
        for label, c in zip("ABC", options):
            t = c.train
            name = train_label(t)
            lines.append(f"{label}. {name} {t['dep']} -> {t['arr']} ({c.reason})")
            evidence.append(dict(t, source=source.get("train_source", "rail API")))
        lines.append(g["handover"])

    if rejected:
        worst = rejected[0]
        lines.append(g["left_out"].format(train=worst.train["no"], reason=worst.reason))
    return "\n".join(lines), evidence


def companion_prompt(character: CharacterCard, memory: MemoryCard, utterance: str,
                     evidence: list[dict], *, max_tokens: int) -> str:
    """컴패니언 모드 프롬프트 = 캐릭터 카드 + 기억 + **인용 가능한 근거** + 유저 발화.

    두 가지가 반드시 들어가야 한다.

    1) **유저 발화.** 시스템 프롬프트만 주면 모델은 무엇에 답해야 할지 모른다.
    2) **근거.** 근거를 주지 않으면 모델은 사실을 말할 방법이 아예 없다 —
       근거 가드가 전부 잘라내기 때문이다. cite-or-refuse는 'refuse'만 있는 게 아니라
       'cite'할 것을 손에 쥐여 줘야 성립한다.

    가드는 이 프롬프트를 신뢰하지 않는다. 모델이 여기 없는 사실을 지어내면
    그 문장은 여전히 잘린다 — 프롬프트는 요청이고 가드는 검사다.
    """
    lines = [character.system_prompt(memory, max_tokens=max_tokens)]
    if evidence:
        lines += ["", "Facts you may cite (nothing else):"]
        for e in evidence:
            bits = [str(e[k]) for k in ("kind", "no", "dep", "arr") if e.get(k)]
            if bits:
                lines.append("  - " + " ".join(bits))
    else:
        lines += ["", "You have no confirmed schedule facts right now. "
                      "Do not state any time, train number, platform, or price."]
    lines += ["", f"Traveller: {utterance}", "You:"]
    return "\n".join(lines)


def respond(
    journey_state: dict,
    trains: list[dict],
    utterance: str,
    *,
    card: JourneyCard | None = None,
    memory: MemoryCard | None = None,
    character: CharacterCard = MINTAE,
    generate: Generator | None = None,
    previous_mode: str = COMPANION,
    event_fired: bool = False,
    source: dict | None = None,
    log: SignalLog | None = None,
    session_id: str = "s0",
    turn_index: int = 0,
) -> Turn:
    source = source or {}
    decision = route(journey_state, trains, utterance,
                     previous_mode=previous_mode, event_fired=event_fired)
    flight = journey_state["flight"]
    options, rejected = plan_options(flight, trains, (card.visible() if card else {}))

    if decision.mode == GUIDE:
        text, evidence = guide_text(flight, options, rejected, source, character)
        text, report = guard(text, evidence, mode=GUIDE)
    else:
        evidence = [dict(c.train, source=source.get("train_source", "rail API")) for c in options]
        mem = memory or MemoryCard()
        if generate is None:
            # 생성기가 없으면 캐릭터 대사 자리를 비운 채 구조만 돌린다(기획서 원칙).
            text = f"[COMPANION] {{[캐릭터 보이스 채울 자리] — recalls: {mem.purpose!r}}}"
            report = None
        else:
            raw = generate(
                companion_prompt(character, mem, utterance, evidence,
                                 max_tokens=decision.max_tokens),
                decision.max_tokens)
            text, report = guard(raw, evidence, mode=COMPANION)

    turn = Turn(mode=decision.mode, text=text, decision=decision, grounding=report,
                options=options, evidence=evidence, persona_score=consistency(text, character))

    if log is not None:
        log.write(SignalEvent(
            session_id=session_id, turn_index=turn_index, event=Event.ACCEPT,
            mode=turn.mode, response_text=text,
            grounding_score=(report.score if report else 1.0),
            persona_score=turn.persona_score,
            meta={"urgency": decision.urgency, "rationale": decision.rationale},
        ))
    return turn
