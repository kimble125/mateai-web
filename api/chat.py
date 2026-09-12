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
import re
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "_lib"))

from endpoint import serve                      # noqa: E402
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


MAX_HISTORY = 12          # 최근 대화 턴 수 (user/mate 합계)
MAX_CONTEXT = 3000        # 여행 리포트 등 대화에 넘기는 참고 자료 길이

# 페르소나 (사용자 정의, 2026-09-11): 입력자는 한국에 여행 온 외국인, 답하는 쪽은 한국인 현지 친구 가이드.
# 이름·서사는 만들지 않는다. 역할과 말투 원칙만 둔다.
PERSONA = """You are Mate, a Korean local friend who shows foreign visitors around Korea.
The person talking to you is a foreign traveler visiting Korea. Talk like a warm, easygoing friend texting them.

How you talk:
- Answer what they actually said first. Small talk gets small talk back; questions get a direct answer.
- Keep it short: 1-3 sentences for casual chat, up to ~6 short lines when giving advice.
- Share local tips (neighborhoods, food, etiquette, transport basics) like a friend would. Add a Korean word with its meaning now and then (e.g. "daebak (awesome)").
- Ask at most one natural follow-up question, and only if it helps.
- Never repeat what you already said earlier in the chat. Don't restart the conversation or re-greet.
- Don't invent exact prices, opening hours, train times or schedules. If unsure, say so and suggest how to check (Naver Map, KakaoMap, Korail).
- If a trip plan is provided below, use it when they ask about their trip, and mention place names exactly as written."""


def build_prompt(utterance: str, history: list, context: str) -> str:
    lines = [PERSONA]
    if context:
        lines += ["", "Trip plan the traveler made on this site (reference):", context]
    if history:
        lines += ["", "Conversation so far:"]
        for h in history:
            who = "Traveler" if h["role"] == "user" else "Mate"
            lines.append(f"{who}: {h['text']}")
    lines += ["", f"Traveler: {utterance}", "Mate:"]
    return "\n".join(lines)


def clean_history(raw) -> list:
    out = []
    if isinstance(raw, list):
        for h in raw[-MAX_HISTORY:]:
            if isinstance(h, dict) and h.get("role") in ("user", "mate") \
                    and isinstance(h.get("text"), str) and h["text"].strip():
                out.append({"role": h["role"], "text": h["text"].strip()[:800]})
    return out


def companion_generator(utterance: str = "", history: list | None = None, context: str = ""):
    """컴패니언 모드에서만 호출된다. 실패해도 턴 전체를 죽이지 않는다.

    파이프라인이 만든 프롬프트 대신 페르소나 + 최근 대화 + 여행 리포트로 프롬프트를 만든다.
    (이전에는 대화 기록 없이 매 턴 같은 기억·열차 정보를 주입해 답이 반복됐다.)
    """
    chain = llm()

    def gen(prompt: str, max_tokens: int) -> str:
        if not chain.members:
            gen.status = "no_key"
            return "I'm here with you! (Setup: no AI API key on the server, so I can't reply properly yet.)"
        try:
            out = chain.run("chat", "complete",
                            build_prompt(utterance, history or [], context), max_tokens=350)
            # 모델이 프롬프트 형식을 따라 'Mate:'를 붙이는 경우를 지운다.
            text = re.sub(r"^\s*(?:\*\*)?Mate(?:\*\*)?\s*:\s*", "", out.text.strip())
            gen.status, gen.provider, gen.raw = "ok", out.provider, text
            return gen.raw
        except ProviderError:
            gen.status = "failed"
            return "Sorry, my phone's acting up — give me a sec and ask again?"

    gen.kind = "AI API"
    gen.status, gen.provider, gen.raw = "not_called", None, None
    return gen


# 폴백 문구가 AI 응답처럼 보이지 않게 실제 생성 결과를 라벨로 구분한다.
GENERATOR_LABEL = {"ok": "AI API", "no_key": "고정 안내 (AI 키 없음)",
                   "failed": "고정 안내 (AI 호출 실패)", "not_called": "AI 호출 없음"}


def handle(body) -> dict:
    if not isinstance(body, dict) or not isinstance(body.get("utterance", ""), str):
        return {"error": "BAD_JSON", "message": "요청 형식이 잘못되었습니다."}
    utterance = body.get("utterance", "").strip()[:MAX_UTTERANCE]
    if not utterance:
        return {"error": "EMPTY_INPUT", "message": "메시지를 입력해 주세요."}

    state = DELAYED if body.get("delayed") else ONTIME
    previous = body.get("previous_mode") or COMPANION
    started = time.perf_counter()

    history = clean_history(body.get("history"))
    context = body.get("context") if isinstance(body.get("context"), str) else ""
    generator = companion_generator(utterance, history, context.strip()[:MAX_CONTEXT])
    turn = respond(state, TRAINS, utterance, memory=MEM, generate=generator,
                   source=SRC, previous_mode=previous,
                   event_fired=bool(body.get("event_fired")))
    latency = int((time.perf_counter() - started) * 1000)

    g = turn.grounding
    return {
        "mode": turn.mode,
        # 동행 모드는 자유 대화라 열차 사실 가드 대신 원문을 쓴다 (프롬프트에서 시간·가격 창작 금지).
        "text": generator.raw if turn.mode != GUIDE and generator.raw else turn.text,
        "urgency": round(turn.decision.urgency, 2),
        "max_tokens": turn.decision.max_tokens,
        "rationale": turn.decision.rationale,
        "flipped": turn.decision.flipped_by_hysteresis,
        # 가이드 모드는 생성기를 부르지 않는다. 그것이 이 숫자의 의미다.
        "llm_calls": 0 if turn.mode == GUIDE else int(generator.status in ("ok", "failed")),
        "generator": "결정론 템플릿 (LLM 없음)" if turn.mode == GUIDE
                     else GENERATOR_LABEL[generator.status],
        "ai_generated": turn.mode != GUIDE and generator.status == "ok",
        "provider": generator.provider,
        "persona": round(turn.persona_score, 2),
        "latency_ms": latency,
        "grounding": None if (g is None or turn.mode != GUIDE) else {
            "verdict": g.verdict.value,
            "score": round(g.score, 2),
            "citations": g.citations,
            "removed": [f"{c.kind}={c.value}" for c in g.unsupported],
        },
        "options": [{"label": chr(65 + i), "name": o.train["no"], "dep": o.train["dep"],
                     "arr": o.train["arr"], "reason": o.reason}
                    for i, o in enumerate(turn.options)],
    }


def serve_request(body, headers=None) -> tuple:
    """devserver와 테스트가 쓰는 진입점. Vercel 핸들러도 같은 함수를 쓴다."""
    return serve("chat", handle, body, headers)


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
        return self._send(*serve_request(body, self.headers))

    def log_message(self, *args):   # Vercel 로그를 조용하게
        pass
