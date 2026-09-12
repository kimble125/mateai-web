"""공개된 엔드포인트가 유료 API를 무제한으로 부르지 않게 막는 최소 장치.

서버리스에는 공유 저장소가 없다. 이 모듈은 **함수 인스턴스 하나의 메모리**만 쓴다.
그래서 다음을 보장하지 못한다.

  - 인스턴스가 여러 개로 늘어나면 전체 호출 수는 여기 상한 × 인스턴스 수까지 늘 수 있다.
  - 인스턴스가 재활용되면 카운터가 0으로 돌아간다.

보장하는 것은 하나다. **한 사람이 한 인스턴스를 붙잡고 연타하는 경로를 막는다.**
정확한 전역 상한이 필요하면 Upstash/Vercel KV 같은 외부 저장소가 필요하며,
그것은 새 비용·새 의존성이라 사용자 승인 대상이다. 여기서는 도입하지 않았다.
"""

import os
import time
from collections import defaultdict, deque

# (요청 수, 초). 여행 리포트는 한 번에 LLM 3회 + 지도 2회라 더 촘촘하게 막는다.
LIMITS = {
    "chat": (int(os.environ.get("CHAT_RATE_LIMIT") or 12), 300),
    "travel": (int(os.environ.get("TRAVEL_RATE_LIMIT") or 4), 600),
}
# 인스턴스가 살아 있는 동안의 총 상한. 링크가 퍼졌을 때의 마지막 방어선이다.
INSTANCE_CAP = {
    "chat": int(os.environ.get("CHAT_INSTANCE_CAP") or 300),
    "travel": int(os.environ.get("TRAVEL_INSTANCE_CAP") or 60),
}

_hits: dict = defaultdict(deque)
_totals: dict = defaultdict(int)


def client_key(headers) -> str:
    """프록시 뒤의 방문자 구분용 키. 원본 IP는 저장하지 않고 앞부분만 쓴다."""
    raw = (headers.get("x-forwarded-for") or headers.get("x-real-ip") or "") if headers else ""
    ip = raw.split(",")[0].strip() or "unknown"
    return ip


def check(kind: str, key: str, *, now: float | None = None) -> dict | None:
    """제한에 걸리면 오류 payload, 통과하면 None. 통과 시에만 사용량을 센다."""
    limit, window = LIMITS[kind]
    now = time.time() if now is None else now

    if _totals[kind] >= INSTANCE_CAP[kind]:
        return {"error": "BUDGET_EXHAUSTED", "retry_after": 3600,
                "message": "This demo has used up its AI budget for now. Please try again later."}

    hits = _hits[(kind, key)]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= limit:
        # limit이 0이면 hits가 비어 있을 수 있다 — 창 전체를 대기 시간으로 본다.
        wait = window - (now - hits[0]) if hits else window
        return {"error": "RATE_LIMITED", "retry_after": int(wait) + 1,
                "message": f"You're going a bit fast. Try again in about "
                           f"{max(1, round(wait / 60))} minute(s)."}

    hits.append(now)
    _totals[kind] += 1
    return None


def reset() -> None:
    """테스트용."""
    _hits.clear()
    _totals.clear()
