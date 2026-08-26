"""POST /api/chat — MateAI 한 턴.

이 엔드포인트의 핵심은 **가이드 모드에 LLM 호출 경로가 없다**는 것이다.
서버리스에서 그 불변식은 설계 주장이 아니라 **비용과 지연으로 증명된다**.
  가이드    : 순수 Python — LLM 호출 0회, 과금 0원, 수 ms
  컴패니언  : AI API 1회 — 과금 발생, 수백 ms~수 초

요청  {"utterance": "...", "delayed": bool, "previous_mode": "guide"|"companion"}
응답  {"mode", "text", "urgency", "max_tokens", "rationale", "llm_calls",
       "latency_ms", "grounding": {...}, "options": [...], "generator"}
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "_lib"))

from persona import MINTAE, MemoryCard          # noqa: E402
from pipeline import respond                     # noqa: E402
from providers import ProviderError, llm         # noqa: E402
from router import COMPANION, GUIDE              # noqa: E402

TRAINS = [
    {"no": "KTX-153", "dep": "17:00", "arr": "18:45", "kind": "KTX"},
    {"no": "KTX-169", "dep": "20:30", "arr": "22:15", "kind": "KTX"},
    {"no": "ITX-1045", "dep": "21:10", "arr": "22:58", "kind": "ITX-새마을"},
]
SRC = {"flight_source": "인천국제공항공사 여객편 운항현황(샘플)",
       "train_source": "국토교통부 TAGO 열차정보(샘플)"}
MEM = MemoryCard(purpose="the station in your mom's old photo", destination="Dongdaegu")

ONTIME = {"flight": {"flight_no": "KE082", "scheduled": "14:30", "estimated": None,
                     "status": "ON_TIME"}, "original_train": "ITX-1045"}
DELAYED = {"flight": {"flight_no": "KE082", "scheduled": "14:30", "estimated": "16:10",
                      "status": "DELAYED"}, "original_train": "KTX-153"}

MAX_UTTERANCE = 500


def companion_generator():
    """컴패니언 모드에서만 호출된다. 실패해도 턴 전체를 죽이지 않는다."""
    chain = llm()

    def gen(prompt: str, max_tokens: int) -> str:
        if not chain.members:
            return "I'm here with you. (설정: AI API 키가 없어 캐릭터 응답을 만들 수 없습니다.)"
        try:
            return chain.run("chat", "complete", prompt, max_tokens=min(max_tokens, 160)).text
        except ProviderError:
            return "Give me a second — I'll check and come back to you."

    gen.kind = "AI API"
    return gen


def handle(body: dict) -> dict:
    utterance = str(body.get("utterance", "")).strip()[:MAX_UTTERANCE]
    if not utterance:
        return {"error": "EMPTY_INPUT", "message": "메시지를 입력해 주세요."}

    state = DELAYED if body.get("delayed") else ONTIME
    previous = body.get("previous_mode") or COMPANION
    started = time.perf_counter()

    generator = companion_generator()
    turn = respond(state, TRAINS, utterance, memory=MEM, generate=generator,
                   source=SRC, previous_mode=previous,
                   event_fired=bool(body.get("event_fired")))
    latency = int((time.perf_counter() - started) * 1000)

    g = turn.grounding
    return {
        "mode": turn.mode,
        "text": turn.text,
        "urgency": round(turn.decision.urgency, 2),
        "max_tokens": turn.decision.max_tokens,
        "rationale": turn.decision.rationale,
        "flipped": turn.decision.flipped_by_hysteresis,
        # 가이드 모드는 생성기를 부르지 않는다. 그것이 이 숫자의 의미다.
        "llm_calls": 0 if turn.mode == GUIDE else 1,
        "generator": "결정론 템플릿 (LLM 없음)" if turn.mode == GUIDE else "AI API",
        "persona": round(turn.persona_score, 2),
        "latency_ms": latency,
        "grounding": None if g is None else {
            "verdict": g.verdict.value,
            "score": round(g.score, 2),
            "citations": g.citations,
            "removed": [f"{c.kind}={c.value}" for c in g.unsupported],
        },
        "options": [{"label": chr(65 + i), "name": o.train["no"], "dep": o.train["dep"],
                     "arr": o.train["arr"], "reason": o.reason}
                    for i, o in enumerate(turn.options)],
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "BAD_JSON", "message": "요청 형식이 잘못되었습니다."})
        try:
            result = handle(body)
        except Exception as e:                                   # noqa: BLE001
            return self._send(500, {"error": type(e).__name__,
                                    "message": "서버에서 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."})
        return self._send(400 if result.get("error") else 200, result)

    def log_message(self, *args):   # Vercel 로그를 조용하게
        pass
