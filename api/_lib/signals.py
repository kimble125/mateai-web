"""유저 행동 신호 — 학습 신호의 원재료.

기획서 §4-6은 "수집 설계까지"였고 스키마가 없었다. 이 모듈이 스키마와 로깅이다.

설계 근거 (스캐터랩 기술블로그 「제타에 Preference Optimization 도입하기」 계승):
  '답변 재생성'을 선호 신호로 쓴다 -- (rejected = 재생성을 유발한 답변,
   chosen = 재생성 후 사용자가 받아들인 답변).
  단, 원시 쌍만으로는 개선이 없었다는 것이 그 글의 핵심 교훈이다.
  따라서 스키마 단계에서 정제에 필요한 필드를 **미리** 남긴다:
  유저별 재생성 습관, 가입 경과, 재생성 횟수, 발화 모드.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


# 불만 발화 패턴 — 「읽씹할 결심」(스캐터랩)의 역추적 방법을 이 도메인에 옮긴 것.
# 그 글은 '지연 답변이 필요했는데 못 한 상황'을 유저 발화("그만 좀 답해", "나 진짜 가야해")로
# 찾아내 50% 이상의 정확도를 얻었다. 같은 발상: **재생성 버튼은 누르는 사람만 누르지만
# 불만은 말로 새어 나온다.** 버튼에만 의존하면 조용히 실망한 유저를 통째로 놓친다.
COMPLAINT_CUES = (
    "that's not what i asked", "thats not what i asked", "you already said",
    "i told you already", "i already told you", "are you sure", "is that right",
    "that's wrong", "thats wrong", "you're not listening", "never mind",
    "forget it", "you don't understand", "왜 자꾸", "아까 말했", "그게 아니라", "이상해",
)


def detect_complaint(utterance: str) -> bool:
    """사용자 발화가 직전 답변에 대한 불만인지 판정한다.

    이것은 라우터의 CRISIS_CUES와 다르다. 위기 신호는 '여정이 급하다'이고,
    불만 신호는 '방금 답이 나빴다'이다 -- 후자만 선호 학습의 rejected 후보가 된다.
    """
    u = utterance.lower()
    return any(c in u for c in COMPLAINT_CUES)


class Event(str, Enum):
    THUMB_UP = "thumb_up"
    THUMB_DOWN = "thumb_down"
    REGENERATE = "regenerate"
    ACCEPT = "accept"            # 재생성 후 그 답변으로 대화를 이어감
    MODE_SWITCH = "mode_switch"  # 사용자가 수동으로 모드를 바꿈 = 라우터 오분류 신호
    COMPLAINT = "complaint"      # 발화로 새어 나온 불만 = 버튼을 누르지 않은 rejected
    HANDOFF = "handoff"          # 공식 채널로 인계
    SESSION_END = "session_end"


@dataclass
class SignalEvent:
    """익명 세션 로그 한 줄. 개인 식별 정보는 담지 않는다."""

    session_id: str
    turn_index: int
    event: Event
    mode: str                       # guide | companion  <- 학습 경계의 근거
    response_text: str = ""
    regen_index: int = 0            # 이 턴에서 몇 번째 재생성인가 (0 = 원본)
    user_account_age_days: int = 0  # 신규 유저 필터용
    user_regen_rate: float = 0.0    # 이 유저의 평소 재생성 비율 (습관적 재생성 필터용)
    grounding_score: float = 1.0    # grounding.check() 결과
    persona_score: float = 1.0      # persona.consistency() 결과
    safety_risk: float = 0.0        # 세이프티 모델 위험점수 (0=안전)
    latency_ms: int = 0
    meta: dict = field(default_factory=dict)

    def to_json(self) -> str:
        d = asdict(self)
        d["event"] = self.event.value
        return json.dumps(d, ensure_ascii=False)


class SignalLog:
    """append-only JSONL 로거. 세션 만료 시 파기하는 것이 운영 원칙."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, ev: SignalEvent) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(ev.to_json() + "\n")

    def read(self) -> list[SignalEvent]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            d["event"] = Event(d["event"])
            out.append(SignalEvent(**d))
        return out
