"""POST /api/travel — 여행 리포트 생성 (A1-2의 파이프라인을 웹으로).

LLM이 지역·날씨·행사를 추천하고, 지도 API가 맛집을 찾고, 다시 LLM이 리포트를 쓴다.
그리고 **리포트에 적힌 가게가 실제 검색 결과에 있는지 검사한다.**

요청  {"date": "YYYY-MM-DD", "cities": 1|2}
응답  {"markdown", "cities", "places", "grounding": {...}, "errors": [...]}
"""

import json
import re
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "_lib"))

from endpoint import serve                                 # noqa: E402
import travel_grounding                                    # noqa: E402
from providers import Chain, ProviderError, llm, places    # noqa: E402

# 영어권 여행자용 제목. '맛집'은 근거 검사(travel_grounding)가 맛집 섹션을 찾는 표식이라 남긴다.
SECTIONS = ("Destinations", "Why Go", "Weather (estimate)", "Events (estimate)",
            "Where to Eat · 맛집", "One-Day Plan")
MAX_CITIES = 2          # 서버리스 실행 시간 제한을 고려해 웹에서는 2곳까지
SPOTS = 5


def parse_json_loose(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.lstrip().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("응답에서 JSON을 찾지 못했습니다")
    return json.loads(cleaned[start:end + 1])


def recommend(chain: Chain, travel_date: str, n: int, errors: list) -> dict | None:
    schema = {"recommended_cities": ["도시명"], "weather": "날씨 요약",
              "events": ["행사 후보"], "reason": "추천 근거 2~3문장"}
    for attempt in (1, 2):
        prompt = (
            f"여행 날짜는 {travel_date} 입니다.\n"
            f"이 시기에 여행하기 좋은 대한민국 국내 도시 {n}곳을 추천해 주세요.\n\n"
            f"아래 스키마에 맞춰 JSON만 출력하세요.\n"
            f"{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"- recommended_cities 는 정확히 {n}개\n"
            "- 도시명은 지도 검색에 쓰므로 '제주', '강릉'처럼 짧게\n"
            "- 날씨·행사는 확정이 아니라 그 시기의 일반적 경향으로\n"
            "- weather, events, reason 값은 외국인 여행자용 자연스러운 영어로\n"
            + ("\n**이전 응답이 JSON으로 파싱되지 않았습니다. 필수 키만 다시 JSON으로.**\n"
               if attempt == 2 else ""))
        try:
            out = chain.run("recommend", "complete", prompt, max_tokens=700, json_mode=True)
        except ProviderError as e:
            errors.append({"step": "recommend", "type": "PROVIDER_ERROR", "message": str(e)})
            return None
        try:
            data = parse_json_loose(out.text)
        except (ValueError, json.JSONDecodeError) as e:
            errors.append({"step": "recommend", "type": "PARSE_ERROR",
                           "message": f"시도 {attempt}: {e}"})
            if attempt == 2:
                return None          # 재시도는 1회로 끝. 무한 재시도 금지.
            continue

        cities = data.get("recommended_cities") or data.get("recommended_city") or []
        if isinstance(cities, str):
            cities = [cities]
        cities = [str(c).strip() for c in cities if str(c).strip()][:n]
        if not cities:
            errors.append({"step": "recommend", "type": "EMPTY_CITY", "message": "추천 도시 없음"})
            if attempt == 2:
                return None
            continue

        events = data.get("events") or []
        if isinstance(events, str):
            events = [events]
        return {"recommended_cities": cities,
                "weather": str(data.get("weather", "")).strip(),
                "events": [str(e).strip() for e in events][:3],
                "reason": str(data.get("reason", "")).strip(),
                "provider": out.provider}
    return None


def search(chain: Chain, cities: list, errors: list) -> dict:
    """실패해도 예외를 올리지 않는다 — 빈 목록으로 다음 단계에 넘긴다."""
    found = {}
    for city in cities:
        try:
            r = chain.run("place_search", "search", f"{city} 맛집", SPOTS)
            found[city] = [{"name": p.name, "address": p.address, "category": p.category,
                            "url": p.url, "source": r.provider} for p in r.places]
            if not found[city]:
                errors.append({"step": "place_search", "city": city,
                               "type": "EMPTY_RESULT", "message": "검색 결과 0건"})
        except ProviderError as e:
            errors.append({"step": "place_search", "city": city,
                           "type": "PROVIDER_ERROR", "message": str(e)})
            found[city] = []
    return found


def write_report(chain: Chain, travel_date: str, rec: dict, by_city: dict,
                 errors: list) -> str:
    lines = [f"Write a Korea trip report for {travel_date} in Markdown, in natural English "
             "for a foreign traveler visiting Korea for the first time.", "",
             f"Destinations: {', '.join(rec['recommended_cities'])}",
             f"Weather (estimate): {rec['weather']}",
             f"Events (estimate): {', '.join(rec['events']) or 'none'}",
             f"Why go: {rec['reason']}", "",
             "Restaurants found by map search — **you may mention ONLY these**:"]
    for city, items in by_city.items():
        lines.append(f"[{city}]")
        lines += [f"  - {p['name']} | {p['address']} | {p['category']}" for p in items] \
            or ["  (검색 결과 없음)"]
    lines += ["", "Rules:",
              "1. Headings in this order: " + " ".join(f"`## {h}`" for h in SECTIONS),
              "2. Where to Eat: only restaurants from the list above. Format "
              "`- **<Korean name exactly as listed>** — <one-line English description> (<address>)`",
              "3. For a city with no search results write `- No data (0 place search results)`",
              "4. Mark weather and events with '(estimate)'",
              "5. City names: English with Korean in parentheses, e.g. Gangneung (강릉)",
              "6. Markdown body only. No code fences."]
    try:
        out = chain.run("report", "complete", "\n".join(lines), max_tokens=1600)
    except ProviderError as e:
        errors.append({"step": "report", "type": "PROVIDER_ERROR", "message": str(e)})
        return fallback(travel_date, rec, by_city)

    text = out.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.lstrip().startswith("markdown"):
            text = text.lstrip()[8:]
    return text.strip()


def fallback(travel_date: str, rec: dict, by_city: dict) -> str:
    h = SECTIONS
    out = [f"# Korea trip plan · {travel_date}", "",
           "> ⚠️ The AI writer failed, so this is a minimal plan built directly from the data.", "",
           f"## {h[0]}", *[f"- {c}" for c in rec["recommended_cities"]], "",
           f"## {h[1]}", rec["reason"] or "(none)", "",
           f"## {h[2]}", f"{rec['weather'] or '(none)'} (estimate)", "",
           f"## {h[3]}", *([f"- {e} (estimate)" for e in rec["events"]] or ["- (none)"]), "",
           f"## {h[4]}"]
    for city, items in by_city.items():
        out.append(f"### {city}")
        out += [f"- **{p['name']}** — {p['category']} ({p['address']})" for p in items] \
            or ["- No data (0 place search results)"]
    out += ["", f"## {h[5]}"]
    for i, city in enumerate(rec["recommended_cities"], 1):
        picks = [p["name"] for p in by_city.get(city, [])[:2]]
        meal = f" — try: {', '.join(picks)}" if picks else ""
        out.append(f"{i}. Explore {city}{meal}")
    return "\n".join(out)


def handle(body) -> dict:
    if not isinstance(body, dict):
        return {"error": "BAD_JSON", "message": "요청 본문은 JSON 객체여야 합니다."}
    if not isinstance(body.get("date"), str):
        return {"error": "BAD_DATE", "message": "날짜를 YYYY-MM-DD 형식으로 입력해 주세요."}
    raw_date = body["date"].strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
        return {"error": "BAD_DATE", "message": "날짜를 YYYY-MM-DD 형식으로 입력해 주세요."}
    try:
        travel_date = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return {"error": "BAD_DATE", "message": f"존재하지 않는 날짜입니다: {raw_date}"}

    n = body.get("cities", 1)
    # bool은 int의 하위 타입이라 따로 막는다. "2" 같은 문자열·5 같은 범위 밖 값은 조용히 고치지 않는다.
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_CITIES:
        return {"error": "BAD_CITIES", "message": f"추천 지역 수는 1~{MAX_CITIES} 사이 정수여야 합니다."}
    llm_chain, place_chain = llm(), places()
    if not llm_chain.members:
        return {"error": "NO_LLM_KEY",
                "message": "서버에 AI API 키가 설정되지 않았습니다. 관리자에게 문의해 주세요."}

    errors: list = []
    rec = recommend(llm_chain, travel_date, n, errors)
    if rec is None:
        return {"error": "RECOMMEND_FAILED",
                "message": "추천 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
                "errors": errors}

    by_city = search(place_chain, rec["recommended_cities"], errors) \
        if place_chain.members else {c: [] for c in rec["recommended_cities"]}
    if not place_chain.members:
        errors.append({"step": "place_search", "type": "NO_KEY",
                       "message": "지도 API 키 없음 — 맛집은 '데이터 없음'으로 진행"})

    markdown = write_report(llm_chain, travel_date, rec, by_city, errors)

    all_places = [p for v in by_city.values() for p in v]
    sources = sorted({p["source"] for p in all_places if p.get("source")})
    guard = travel_grounding.check(markdown, all_places, sources)
    markdown = travel_grounding.annotate(markdown, guard)

    errors.extend(llm_chain.errors)
    errors.extend(place_chain.errors)
    return {
        # 다음 제공자로 넘어가 성공한 기록(fell_back)은 결과 누락이 아니므로 partial로 세지 않는다.
        "status": "partial" if any(not e.get("fell_back") for e in errors) else "complete",
        "date": travel_date,
        "markdown": markdown,
        "cities": rec["recommended_cities"],
        "places": by_city,
        "grounding": {"verdict": guard.verdict.value, "score": round(guard.score, 2),
                      "checked": len(guard.claims),
                      "unsupported": [c.value for c in guard.unsupported],
                      "sources": guard.sources},
        "errors": errors,
    }


def serve_request(body, headers=None) -> tuple:
    """devserver와 테스트가 쓰는 진입점. Vercel 핸들러도 같은 함수를 쓴다."""
    return serve("travel", handle, body, headers)


class handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
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

    def log_message(self, *args):
        pass
