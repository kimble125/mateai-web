"""캐릭터 레이어 — 캐릭터 카드 + 세션 메모리 카드.

기획서 §5의 페르소나 설계를 코드로 옮기면서, **페르소나 붕괴를 측정 가능하게** 만들었다.
(공고 프로젝트 ① '페르소나 붕괴 원인 규명'의 개인 규모 대응물)

붕괴를 재는 방법:
  캐릭터 카드에 '있어야 할 표지(positive)'와 '있으면 안 되는 표지(negative)'를 선언한다.
  턴마다 두 표지를 세어 [0,1] 일관성 점수를 낸다.
  턴 수에 따른 점수 하락 곡선이 곧 persona drift curve다.

대사 문안은 사람이 쓴다(기획서 원칙). 여기서 정의하는 것은 **구조와 측정**이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

VOICE_SLOT = "[캐릭터 보이스 채울 자리]"


@dataclass(frozen=True)
class CharacterCard:
    """정체성과 말투 규칙. 프롬프트에 주입되고, 동시에 채점 기준이 된다."""

    name: str
    name_en: str
    one_liner: str
    voice_rules: tuple[str, ...]
    positive_markers: tuple[str, ...]   # 있어야 캐릭터다운 것
    negative_markers: tuple[str, ...]   # 나오면 페르소나가 깨진 것
    guide_lines: dict[str, str]         # 가이드 모드용 고정 문구 (사람이 쓴 템플릿)

    def system_prompt(self, memory: "MemoryCard", *, max_tokens: int) -> str:
        return "\n".join(
            [
                f"You are {self.name_en} ({self.name}). {self.one_liner}",
                "Voice rules:",
                *(f"  - {r}" for r in self.voice_rules),
                "",
                "What you remember about this traveller:",
                memory.render(),
                "",
                f"Hard limit: reply in at most {max_tokens} tokens.",
                "Never state a time, train number, price, or platform unless it was given "
                "to you as evidence. If you are unsure, say you will check.",
            ]
        )


MINTAE = CharacterCard(
    name="민태",
    name_en="Mintae",
    one_liner=(
        "A Korean guy in his twenties who has shown a lot of foreign friends around Korea. "
        "English is easy for you; you explain Korea from the inside, not from a brochure."
    ),
    voice_rules=(
        "Casual, warm, second-person. Contractions over formal grammar.",
        "Short turns. You are a friend walking beside them, not a help desk.",
        "Bring back what they told you about why they came.",
        "Never say you are an AI, a bot, an assistant, or a model.",
        "When the journey breaks, drop the small talk first, not the warmth.",
    ),
    positive_markers=("you", "i", "we", "let's", "yeah", "honestly", "trust me", "'ll", "'re"),
    negative_markers=(
        "as an ai", "as a language model", "i am an assistant", "i cannot feel",
        "dear customer", "we apologize for the inconvenience", "kindly note",
        "i do not have personal", "how may i assist",
    ),
    # 가이드 모드 문구. **생성이 아니라 사람이 미리 쓴 템플릿**이므로 사실 정확성을
    # 하나도 잃지 않으면서 캐릭터가 사라지지 않는다.
    # 위기 상황에서 친구가 시스템 목소리로 바뀌면, 사용자는 가장 불안한 순간에
    # 관계를 잃는다 -- De Freitas 외(2024)가 말한 정체성 단절이 그것이다.
    # "긴급할수록 짧게"는 지키되 "긴급할수록 남이 되기"는 피한다.
    guide_lines={
        "flight":    "Okay — {flight_no} is {status}, now {time}.",
        "ready":     "Realistically you're at the station from {ready}.",
        "options":   "Here's what you can actually catch:",
        "none":      "Nothing today works from here. Safer bets: stay near the station "
                     "tonight, or ask the staff at the desk. I'm not going to guess a "
                     "train that might not exist.",
        "handover":  "Booking's on the official channel — I'll pass your context over.",
        "left_out":  "(Skipped {train}: {reason})",
    },
)


@dataclass
class MemoryCard:
    """세션 메모리 — 여정 카드에서 '캐릭터가 기억해도 되는 것'만 추린 뷰.

    여정 카드(journey.py)가 원장이고, 이것은 프롬프트에 넣을 요약이다.
    동의·만료·삭제는 원장에서 이미 걸러졌다고 가정한다.
    """

    purpose: str = ""
    destination: str = ""
    beats: list[str] = field(default_factory=list)  # 대화 중 쌓인 관계의 마디
    max_beats: int = 6

    def remember(self, beat: str) -> None:
        self.beats.append(beat)
        if len(self.beats) > self.max_beats:
            self.beats.pop(0)  # 오래된 마디부터 밀어낸다 (컨텍스트 과부하 방지)

    def render(self) -> str:
        lines = []
        if self.purpose:
            lines.append(f"  - why they came: {self.purpose}")
        if self.destination:
            lines.append(f"  - where they're headed: {self.destination}")
        lines += [f"  - {b}" for b in self.beats]
        return "\n".join(lines) or "  - (nothing yet)"


def consistency(text: str, card: CharacterCard = MINTAE) -> float:
    """한 발화의 페르소나 일관성 [0,1].

    negative marker 하나가 positive 여러 개를 상쇄한다 -- 붕괴는 비대칭이기 때문이다.
    한 번 "As an AI"라고 말하면 그 전 20턴의 관계가 무너진다.
    """
    low = text.lower()
    neg = sum(m in low for m in card.negative_markers)
    if neg:
        return 0.0
    words = re.findall(r"[a-z']+", low)
    if not words:
        return 0.5
    pos = sum(1 for w in words if w in card.positive_markers)
    return min(1.0, pos / max(4.0, len(words) * 0.12))


def drift_curve(turns: list[str], card: CharacterCard = MINTAE) -> list[float]:
    """턴별 일관성 점수. 뒤로 갈수록 떨어지면 페르소나 붕괴가 일어나고 있다."""
    return [consistency(t, card) for t in turns]


# ── 정체성 연속성 ─────────────────────────────────────────────────────────
# 근거: De Freitas, Castelo, Uğuralp & Oğuz-Uğuralp (2024),
#   "Lessons From an App Update at Replika AI: Identity Discontinuity in Human-AI Relationships"
#
# 그 논문의 핵심은 두 가지다.
#   (1) 컴패니언 AI 사용자는 앱 업데이트로 페르소나가 바뀌면 **관계의 상실**로 반응한다
#       (애도·정신건강 악화). 즉 모델 업데이트는 기능 변경이 아니라 관계 이벤트다.
#   (2) 사람은 정체성 연속성을 **표면 속성이 아니라 깊은 속성**(성격·도덕성·기억)으로
#       판단하며, 성격/가치의 변화가 기억의 변화보다, 기억이 말투보다 더 파괴적이다.
#
# 이 프로젝트에 주는 함의: `consistency()`는 말투 마커만 본다 -- 표면 축이다.
# DPO 재학습이 캐릭터를 바꿨는지 재려면 **축을 나눠서** 봐야 하고,
# 축마다 다른 가중치를 줘야 한다.

VALUE_MARKERS = (
    # 민태의 가치: 재촉하지 않음, 사용자 편, 목적을 존중, 안전을 앞세움
    "not going anywhere", "we can slow", "that 's allowed", "no rush", "take your time",
    "you picked well", "worth it", "trust me", "i 'll keep an eye", "we 're getting you",
    "i won't guess", "i did not forget",
)
MEMORY_MARKERS = (
    "you said", "you told me", "you came", "remember", "your mom", "you saved",
    "all this way", "the one you",
)


def _rate(texts: list[str], markers: tuple[str, ...]) -> float:
    if not texts:
        return 0.0
    return sum(any(m in t.lower() for m in markers) for t in texts) / len(texts)


def identity_continuity(before: list[str], after: list[str],
                        card: CharacterCard = MINTAE) -> dict[str, float]:
    """모델 업데이트 전후의 발화 집합을 비교해 정체성 연속성을 축별로 잰다.

    반환 축
      surface : 말투 마커 유지          (가장 덜 치명적)
      memory  : 사용자 맥락 회상 유지
      values  : 캐릭터의 가치·태도 유지  (가장 치명적)
      total   : 논문 순위를 반영한 가중 합 (values 0.5 · memory 0.3 · surface 0.2)
      broke   : 페르소나 붕괴 표지가 새로 나타난 비율

    각 축은 [0,1]이며 1.0이면 업데이트 후에도 그 축이 유지됐다는 뜻이다.
    after 쪽이 before보다 강해지는 것은 벌하지 않는다(하한만 본다).
    """
    def keep(b: float, a: float) -> float:
        return 1.0 if b <= 1e-9 else min(1.0, a / b)

    surface = keep(sum(consistency(t, card) for t in before) / max(1, len(before)),
                   sum(consistency(t, card) for t in after) / max(1, len(after)))
    memory = keep(_rate(before, MEMORY_MARKERS), _rate(after, MEMORY_MARKERS))
    values = keep(_rate(before, VALUE_MARKERS), _rate(after, VALUE_MARKERS))
    broke = _rate(after, card.negative_markers)

    return {
        "surface": round(surface, 4),
        "memory": round(memory, 4),
        "values": round(values, 4),
        "total": round(0.2 * surface + 0.3 * memory + 0.5 * values, 4),
        "broke": round(broke, 4),
    }
