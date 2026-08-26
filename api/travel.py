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

import travel_grounding                                    # noqa: E402
from providers import Chain, ProviderError, llm, places    # noqa: E402

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
    lines = [f"{travel_date} 국내 여행 리포트를 마크다운으로 작성하세요.", "",
             f"추천 지역: {', '.join(rec['recommended_cities'])}",
             f"날씨(추정): {rec['weather']}",
             f"행사(추정): {', '.join(rec['events']) or '없음'}",
             f"추천 이유: {rec['reason']}", "",
             "검색된 맛집 — **이 목록의 가게만 언급할 수 있습니다**:"]
    for city, items in by_city.items():
        lines.append(f"[{city}]")
        lines += [f"  - {p['name']} | {p['address']} | {p['category']}" for p in items] \
            or ["  (검색 결과 없음)"]
    lines += ["", "규칙:",
              "1. 제목 순서: `## 추천 지역` `## 추천 이유` `## 날씨 요약` `## 행사·축제` "
              "`## 맛집 추천` `## 1일 일정 제안`",
              "2. 맛집 섹션은 위 목록의 가게만. 형식 `- **가게이름** — 주소 (카테고리)`",
              "3. 검색 결과 없는 지역은 `- 데이터 없음 (장소 검색 결과 0건)`",
              "4. 날씨·행사에는 반드시 '(추정)' 을 붙일 것",
              "5. 마크다운 본문만. 코드블록으로 감싸지 말 것"]
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
    out = [f"# {travel_date} 국내 여행 리포트", "",
           "> ⚠️ AI 호출에 실패해 자료를 그대로 정리한 최소 리포트입니다.", "",
           "## 추천 지역", *[f"- {c}" for c in rec["recommended_cities"]], "",
           "## 추천 이유", rec["reason"] or "(없음)", "",
           "## 날씨 요약", f"{rec['weather'] or '(없음)'} (추정)", "",
           "## 행사·축제", *([f"- {e} (추정)" for e in rec["events"]] or ["- (없음)"]), "",
           "## 맛집 추천"]
    for city, items in by_city.items():
        out.append(f"### {city}")
        out += [f"- **{p['name']}** — {p['address']} ({p['category']})" for p in items] \
            or ["- 데이터 없음 (장소 검색 결과 0건)"]
    return "\n".join(out)


def handle(body: dict) -> dict:
    raw_date = str(body.get("date", "")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
        return {"error": "BAD_DATE", "message": "날짜를 YYYY-MM-DD 형식으로 입력해 주세요."}
    try:
        travel_date = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return {"error": "BAD_DATE", "message": f"존재하지 않는 날짜입니다: {raw_date}"}

    n = max(1, min(int(body.get("cities") or 1), MAX_CITIES))
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
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "BAD_JSON", "message": "요청 형식이 잘못되었습니다."})
        try:
            result = handle(body)
        except Exception as e:                                   # noqa: BLE001
            return self._send(500, {"error": type(e).__name__,
                                    "message": "서버 오류입니다. 잠시 후 다시 시도해 주세요."})
        return self._send(400 if result.get("error") else 200, result)

    def log_message(self, *args):
        pass
