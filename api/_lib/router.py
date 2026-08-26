"""긴급도 라우터 — 가이드 모드 ↔ 컴패니언 모드.

서비스의 중심 장치. "긴급할수록 짧게".

v0(`nextstop.py`) 대비 변경점:
  1. 이진 판정 -> **연속 urgency score [0,1]**. 경계 근처의 애매함을 보존한다.
  2. **히스테리시스**: 모드 진입/이탈 임계값을 분리해 경계에서 모드가 떨리는 것을 막는다.
     관계형 챗봇에서 모드 플래핑은 페르소나 붕괴로 체감된다.
  3. **사용자 발화 의도**를 신호에 포함한다. 여유가 있어도 "지금 어떡해?"면 가이드로 간다.
  4. `features()`를 공개해 **학습형 라우터**(train/router_probe.py)가 같은 입력을 쓰게 한다.
     규칙 라우터 = teacher, 학습 라우터 = student(발화만 보고 선행 예측).

왜 학습형 라우터가 필요한가:
  규칙 라우터는 여정 상태(항공 API)가 바뀐 *뒤에야* 반응한다 -- 후행적이다.
  발화에서 먼저 위기를 감지하면 API 갱신 전에 모드를 올릴 수 있다 -- 선행적이다.
  이는 공고 프로젝트 ④ '후행적 A/B를 보완하는 선행 지표' 문제의 축소판이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from feasibility import ReadyWindow, evaluate, hhmm_to_min, ready_window

GUIDE, COMPANION = "guide", "companion"

# 히스테리시스: 컴패니언 -> 가이드는 쉽게(0.55), 가이드 -> 컴패니언은 어렵게(0.35).
# 위기를 놓치는 비용 > 과잉 경계의 비용, 이라는 비대칭을 임계값에 새긴다.
ENTER_GUIDE_AT = 0.55
LEAVE_GUIDE_AT = 0.35

# 발화 의도 신호. 캐릭터 대사는 사람이 쓰지만, 라우팅 키워드는 결정론이어야 한다.
CRISIS_CUES = (
    "delayed", "missed", "cancel", "late", "stuck", "help", "what do i do",
    "hurry", "urgent", "wrong train", "lost", "지연", "놓쳤", "취소", "어떡",
)
CALM_CUES = (
    "tell me about", "what's it like", "how long have you", "recommend",
    "why do", "story", "궁금", "알려줘", "어떤 곳",
)


@dataclass(frozen=True)
class RouteDecision:
    mode: str
    urgency: float
    features: dict[str, float]
    rationale: str
    max_tokens: int          # 라우터가 발화량을 *강제로* 줄인다
    persona_freedom: bool    # 컴패니언에서만 자유 생성 허용

    @property
    def flipped_by_hysteresis(self) -> bool:
        """점수만 보면 반대 모드였을 상황을 히스테리시스가 붙잡은 경우."""
        if self.mode == GUIDE:
            return self.urgency < ENTER_GUIDE_AT
        return self.urgency > LEAVE_GUIDE_AT


def features(
    journey: dict,
    trains: list[dict],
    utterance: str = "",
    *,
    event_fired: bool = False,
) -> dict[str, float]:
    """라우팅 판단의 원재료. 규칙 라우터와 학습 라우터가 **같은 정의**를 공유한다."""
    flight = journey["flight"]
    window: ReadyWindow = ready_window(flight)

    original = next((t for t in trains if t["no"] == journey.get("original_train")), None)
    if original is None:
        plan_margin = -999.0
    else:
        plan_margin = float(evaluate(original, window).margin_min)

    feasible_left = sum(1 for t in trains if evaluate(t, window).feasible)
    u = utterance.lower()

    return {
        # 여정 상태 (후행 신호 — API가 갱신되어야 움직인다)
        "plan_margin_min": plan_margin,
        "plan_broken": 1.0 if plan_margin < 0 else 0.0,
        "feasible_left": float(feasible_left),
        "no_options": 1.0 if feasible_left == 0 else 0.0,
        "flight_disrupted": 1.0 if flight.get("status") in {"DELAYED", "CANCELLED"} else 0.0,
        "window_uncertain": 1.0 if window.uncertain else 0.0,
        "event_fired": 1.0 if event_fired else 0.0,
        # 발화 의도 (선행 신호 — 사용자가 먼저 말한다)
        "crisis_cue": float(sum(c in u for c in CRISIS_CUES)),
        "calm_cue": float(sum(c in u for c in CALM_CUES)),
        "utterance_len": float(len(u.split())),
    }


def urgency_score(f: dict[str, float]) -> float:
    """[0,1] 긴급도. 가중치는 설계 판단이며, 학습 라우터가 이후 이 곡선을 근사한다."""
    s = 0.0
    s += 0.35 * f["plan_broken"]
    s += 0.20 * f["no_options"]
    s += 0.15 * f["flight_disrupted"]
    s += 0.10 * f["event_fired"]
    s += 0.05 * f["window_uncertain"]
    s += 0.20 * min(f["crisis_cue"], 2.0) / 2.0
    s -= 0.15 * min(f["calm_cue"], 2.0) / 2.0
    # 여유가 아주 많으면(90분+) 상태 기반 긴급도를 감쇠시킨다.
    if f["plan_margin_min"] > 90:
        s -= 0.10
    return max(0.0, min(1.0, s))


def route(
    journey: dict,
    trains: list[dict],
    utterance: str = "",
    *,
    previous_mode: str = COMPANION,
    event_fired: bool = False,
) -> RouteDecision:
    """모드를 결정한다. 이전 모드를 받아 히스테리시스를 적용한다."""
    f = features(journey, trains, utterance, event_fired=event_fired)
    u = urgency_score(f)

    if previous_mode == GUIDE:
        mode = COMPANION if u < LEAVE_GUIDE_AT else GUIDE
    else:
        mode = GUIDE if u >= ENTER_GUIDE_AT else COMPANION

    if mode == GUIDE:
        why = []
        if f["plan_broken"]:
            why.append("your booked train is no longer boardable")
        if f["no_options"]:
            why.append("no feasible train remains today")
        if f["flight_disrupted"]:
            why.append("flight status changed")
        if f["crisis_cue"]:
            why.append("you asked for immediate help")
        rationale = "; ".join(why) or "urgency above threshold"
        # 긴급할수록 짧게: 후보가 없을 때가 가장 짧아야 한다.
        max_tokens = 90 if f["no_options"] else 140
    else:
        rationale = "journey has enough buffer — companion mode"
        max_tokens = 320

    return RouteDecision(
        mode=mode,
        urgency=round(u, 4),
        features=f,
        rationale=rationale,
        max_tokens=max_tokens,
        persona_freedom=(mode == COMPANION),
    )
