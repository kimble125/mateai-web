"""HTTP 경계 한 곳. Vercel 함수와 로컬 devserver가 **같은 경로**를 쓰게 한다.

이 파일이 생긴 이유: devserver가 `handle(body)`를 직접 불러서 호출 제한과
오류 숨김을 건너뛰었다. 로컬에서 통과한 것이 배포에서 통과한다는 보장이 없었다.
"""

import budget


def serve(kind: str, handle_fn, body, headers=None) -> tuple:
    """(status_code, payload). 유료 호출 전에 예산을 먼저 확인한다."""
    try:
        capped = budget.check(kind, budget.client_key(headers))
        if capped:
            return 429, capped
        result = handle_fn(body)
    except Exception as e:                                   # noqa: BLE001
        # 예외 문구를 그대로 내보내지 않는다 — 내부 경로·설정이 드러날 수 있다.
        return 500, {"error": type(e).__name__,
                     "message": "Something went wrong on our side. Please try again."}
    return (400 if result.get("error") else 200), result
