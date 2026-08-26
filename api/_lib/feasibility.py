"""실행 가능성 규칙 엔진 — 결정론 레이어.

`4. 내일로/prototype/nextstop.py` 의 로직을 승격·확장했다(원본은 보존).

v0 대비 변경점:
  1. 상수마다 근거(source)를 붙여 답변에 인용할 수 있게 했다.
  2. 후보를 '통과/탈락' 이진이 아니라 **탈락 사유가 붙은 구조체**로 반환한다.
     -> 사용자에게 "왜 이 열차는 빠졌는지"를 설명할 수 있고,
     -> 컴패니언 레이어가 사실을 지어낼 여지를 없앤다.
  3. 후보 0건 경로를 1급 기능으로 승격했다(기획서 §10-1 타개 계획).
  4. 도착시각을 점추정이 아니라 **구간(lo, hi)** 으로 다뤄 불확실성을 보존한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ── 상수와 그 근거 ────────────────────────────────────────────────────────
# MVP 단계의 보수적 상수. 값 자체보다 '근거가 붙어 있다'는 점이 설계의 핵심이다.
SAFETY_BUFFER_MIN = 30
IMMIGRATION_EST_MIN = (40, 80)
TRANSFER_ICN_TO_SEOUL_MIN = 75

CONSTANT_SOURCES: dict[str, str] = {
    "SAFETY_BUFFER_MIN": "MVP 보수 상수 — 본선에서 공항 공지·실측치로 대체 예정",
    "IMMIGRATION_EST_MIN": "입국심사·수하물 수취 소요 추정 구간 (상한을 기준선으로 사용)",
    "TRANSFER_ICN_TO_SEOUL_MIN": "AREX 직통 + 역 내 환승 도보의 보수 추정",
}


class Reject(str, Enum):
    """후보가 탈락한 이유. 사용자에게 그대로 보여줄 수 있는 어휘."""

    TOO_EARLY = "departs before you can realistically board"
    LUGGAGE = "transfer window too tight with your luggage"
    ACCESSIBILITY = "step-free transfer not confirmed on this route"
    LAST_MILE = "arrives after local transport stops running"


def hhmm_to_min(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def min_to_hhmm(n: int) -> str:
    return f"{n // 60 % 24:02d}:{n % 60:02d}"


@dataclass(frozen=True)
class ReadyWindow:
    """역에서 열차를 탈 준비가 되는 시각의 구간(분). 점추정을 쓰지 않는다."""

    lo: int
    hi: int
    basis: str  # 어떤 항공 필드에서 유도했는지 (scheduled / estimated)

    @property
    def uncertain(self) -> bool:
        return self.hi - self.lo >= 30


@dataclass
class Candidate:
    """열차 후보 하나에 대한 판정 결과."""

    train: dict
    feasible: bool
    rejects: list[Reject] = field(default_factory=list)
    margin_min: int = 0  # 안전 버퍼를 넘긴 여유(분). 음수면 부족분.
    reason: str = ""

    def as_option(self, source: dict) -> dict:
        return {
            **self.train,
            **source,
            "margin_min": self.margin_min,
            "reason": self.reason,
        }


def ready_window(flight: dict) -> ReadyWindow:
    """항공 도착 → 입국·수하물 → 공항-역 이동을 거쳐 탑승 준비가 되는 구간."""
    basis = "estimated" if flight.get("estimated") else "scheduled"
    arrival = hhmm_to_min(flight.get("estimated") or flight["scheduled"])
    lo = arrival + IMMIGRATION_EST_MIN[0] + TRANSFER_ICN_TO_SEOUL_MIN
    hi = arrival + IMMIGRATION_EST_MIN[1] + TRANSFER_ICN_TO_SEOUL_MIN
    return ReadyWindow(lo=lo, hi=hi, basis=basis)


def evaluate(train: dict, window: ReadyWindow, constraints: dict | None = None) -> Candidate:
    """한 열차 후보를 판정한다. 보수적으로 window.hi(최악의 경우)를 기준선으로 쓴다."""
    constraints = constraints or {}
    dep = hhmm_to_min(train["dep"])
    need = window.hi + SAFETY_BUFFER_MIN
    margin = dep - need

    rejects: list[Reject] = []
    if margin < 0:
        rejects.append(Reject.TOO_EARLY)

    # 하드 제약: 사용자가 직접 입력한 조건만 사용한다(AI가 추론하지 않는다).
    if constraints.get("luggage", 0) >= 2 and 0 <= margin < 15:
        rejects.append(Reject.LUGGAGE)
    if constraints.get("accessibility") and not train.get("step_free"):
        rejects.append(Reject.ACCESSIBILITY)
    if train.get("arr") and hhmm_to_min(train["arr"]) >= hhmm_to_min("23:30"):
        rejects.append(Reject.LAST_MILE)

    feasible = not rejects
    reason = (
        f"boardable from {min_to_hhmm(window.hi)} (+{SAFETY_BUFFER_MIN}min buffer); "
        f"{margin}min to spare"
        if feasible
        else "; ".join(r.value for r in rejects)
    )
    return Candidate(train=train, feasible=feasible, rejects=rejects, margin_min=margin, reason=reason)


def plan_options(
    flight: dict, trains: list[dict], constraints: dict | None = None, max_n: int = 3
) -> tuple[list[Candidate], list[Candidate]]:
    """(실행 가능 후보 최대 max_n개, 탈락 후보 전체)를 돌려준다.

    후보가 없으면 빈 리스트를 돌려준다 — 존재하지 않는 열차를 만들어내지 않는다.
    탈락 목록을 함께 돌려주는 것이 이 함수의 핵심: 설명의 근거가 된다.
    """
    window = ready_window(flight)
    judged = [evaluate(t, window, constraints) for t in trains]
    ok = sorted((c for c in judged if c.feasible), key=lambda c: hhmm_to_min(c.train["dep"]))
    no = sorted((c for c in judged if not c.feasible), key=lambda c: hhmm_to_min(c.train["dep"]))
    return ok[:max_n], no


# ── 파생 근거 ─────────────────────────────────────────────────────────────
def derived_evidence(flight: dict, candidates: list[Candidate]) -> list[dict]:
    """규칙 엔진이 **계산한** 값을 근거 항목으로 노출한다.

    왜 필요한가: 근거 검증기(grounding.py)는 '공식 API에 있는 값'만 인정한다.
    그런데 안내문에는 API에 없는 수가 반드시 등장한다 -- 탑승 준비 시각, 안전 버퍼,
    여유 분. 이것들은 환각이 아니라 **결정론적 계산의 산물**이고, 입력과 상수를
    밝히면 완전히 추적 가능하다. 그래서 '출처가 API가 아니라 규칙 엔진'인
    별개의 근거 유형으로 인정한다.

    이 구분이 없으면 둘 중 하나가 된다: 가드가 자기 답변을 막거나(지금 발견한 버그),
    아니면 가드를 느슨하게 풀어 진짜 환각까지 통과시키거나.
    """
    window = ready_window(flight)
    src = (f"MateAI 규칙 엔진 (입력: 항공 도착 {flight.get('estimated') or flight['scheduled']}"
           f" + 입국 {IMMIGRATION_EST_MIN[1]}분 + 이동 {TRANSFER_ICN_TO_SEOUL_MIN}분)")
    items = [{
        "ready_from": min_to_hhmm(window.hi),
        "ready_earliest": min_to_hhmm(window.lo),
        "safety_buffer": f"{SAFETY_BUFFER_MIN}min",
        "immigration": f"{IMMIGRATION_EST_MIN[1]}min",
        "transfer": f"{TRANSFER_ICN_TO_SEOUL_MIN}min",
        "source": src,
    }]
    for c in candidates:
        items.append({
            "train_no": c.train["no"],
            "margin": f"{c.margin_min}min",
            "source": "MateAI 규칙 엔진 (여유 = 출발 − 준비완료 − 안전버퍼)",
        })
    return items
