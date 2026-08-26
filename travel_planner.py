"""국내 여행지 추천 — LLM + 지도 API를 엮어 여행 리포트를 만든다.

    python3 travel_planner.py --date 2026-03-15
    python3 travel_planner.py --date 2026-03-15 --cities 3     # 복수 지역(보너스 1)
    python3 travel_planner.py --date 2026-03-15 --no-cache     # 캐시 무시(보너스 2)

흐름
    1차 추천(LLM) → 맛집 검색(지도 API) → 최종 리포트(LLM) → 근거 가드 → 저장

설계 원칙
    · **한 단계가 실패해도 리포트는 나온다.** 맛집 검색이 죽으면 '데이터 없음'으로 넘긴다.
    · **실패를 숨기지 않는다.** 모든 오류를 errors 목록에 모아 리포트와 JSON에 남긴다.
    · **검증 가능한 것만 검증한다.** 가게 이름은 대조하고, 날씨·행사는 '추정'이라 표시한다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import grounding
from providers import Chain, ProviderError, llm, load_env, places

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

G, R, Y, D, B, X = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"


def log(step: str, message: str, color: str = "") -> None:
    print(f"{D}[{step}]{X} {color}{message}{X}", flush=True)


# ── CLI ─────────────────────────────────────────────────────────────────
def parse_date(value: str) -> str:
    """YYYY-MM-DD 만 받는다. 형식이 틀리면 argparse가 사용법을 찍고 종료한다."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"날짜 형식이 올바르지 않습니다: {value!r} — YYYY-MM-DD 로 입력해 주세요 "
            f"(예: {date.today().isoformat()})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="travel_planner.py",
        description="여행 날짜를 주면 국내 추천 지역·맛집·1일 일정을 담은 리포트를 만듭니다.",
        epilog="API 키는 .env 파일에 넣습니다. .env.example 을 복사해서 쓰세요.")
    p.add_argument("--date", required=True, type=parse_date, metavar="YYYY-MM-DD",
                   help="여행 날짜 (필수)")
    p.add_argument("--cities", type=int, default=1, choices=(1, 2, 3),
                   help="추천받을 지역 수 (기본 1, 최대 3) — 보너스 1")
    p.add_argument("--spots", type=int, default=5, metavar="N",
                   help="지역당 맛집 개수 (기본 5)")
    p.add_argument("--no-cache", action="store_true",
                   help="같은 날짜의 저장된 결과가 있어도 API를 다시 부른다 — 보너스 2")
    return p


# ── 1단계: 1차 추천 (LLM → JSON) ────────────────────────────────────────
RECOMMEND_SCHEMA = {
    "recommended_cities": ["도시명 (문자열)"],
    "weather": "해당 시기의 일반적인 날씨 요약 (문자열)",
    "events": ["행사·축제 후보 (문자열) 1~3개"],
    "reason": "추천 근거 2~4문장 (문자열)",
}


def recommend_prompt(travel_date: str, n_cities: int, strict: bool = False) -> str:
    base = (
        f"여행 날짜는 {travel_date} 입니다.\n"
        f"이 시기에 여행하기 좋은 **대한민국 국내 도시 {n_cities}곳**을 추천해 주세요.\n\n"
        "아래 JSON 스키마에 정확히 맞춰서 **JSON만** 출력하세요. 설명이나 코드블록 표시 없이.\n"
        f"{json.dumps(RECOMMEND_SCHEMA, ensure_ascii=False, indent=2)}\n\n"
        "규칙:\n"
        f"- recommended_cities 는 정확히 {n_cities}개의 문자열 배열\n"
        "- 도시명은 지도 검색에 쓸 것이므로 '제주', '강릉', '경주'처럼 **짧고 일반적인 이름**으로\n"
        "- events 는 1~3개의 문자열 배열\n"
        "- 날씨와 행사는 확정 정보가 아니라 그 시기의 일반적인 경향으로 적으세요\n"
    )
    if strict:
        # 재시도용. 요구를 최소로 줄여 파싱 성공률을 올린다.
        base += "\n**이전 응답이 JSON으로 파싱되지 않았습니다. 필수 키만 다시 JSON으로 출력하세요.**\n"
    return base


def parse_json_loose(text: str) -> dict:
    """```json 코드블록이나 앞뒤 군더더기가 붙어 와도 본문만 뽑아 파싱한다."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.lstrip().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("응답에서 JSON 객체를 찾지 못했습니다")
    return json.loads(cleaned[start:end + 1])


def normalise_recommendation(data: dict, n_cities: int) -> dict:
    """스키마를 맞춘다. 모델이 recommended_city(단수)로 줄 때도 받아 준다."""
    cities = data.get("recommended_cities") or data.get("recommended_city") or []
    if isinstance(cities, str):
        cities = [cities]
    cities = [str(c).strip() for c in cities if str(c).strip()][:n_cities]

    events = data.get("events") or []
    if isinstance(events, str):
        events = [events]

    return {
        "recommended_cities": cities,
        "weather": str(data.get("weather", "")).strip(),
        "events": [str(e).strip() for e in events if str(e).strip()][:3],
        "reason": str(data.get("reason", "")).strip(),
    }


def step_recommend(chain: Chain, travel_date: str, n_cities: int,
                   errors: list[dict]) -> dict | None:
    """LLM 1차 추천. JSON 파싱 실패 시 재시도는 **최대 1회**(과제 제약)."""
    for attempt in (1, 2):
        prompt = recommend_prompt(travel_date, n_cities, strict=(attempt == 2))
        try:
            result = chain.run("recommend", "complete", prompt, max_tokens=800, json_mode=True)
        except ProviderError as e:
            errors.append({"step": "recommend", "type": "PROVIDER_ERROR", "message": str(e)})
            return None

        try:
            data = normalise_recommendation(parse_json_loose(result.text), n_cities)
        except (ValueError, json.JSONDecodeError) as e:
            errors.append({"step": "recommend", "type": "PARSE_ERROR",
                           "message": f"시도 {attempt}: {e}", "provider": result.provider})
            if attempt == 2:
                return None          # 재시도는 여기서 끝. 무한 재시도 금지.
            log("1/3", f"JSON 파싱 실패 — 한 번만 다시 시도합니다", Y)
            continue

        if not data["recommended_cities"]:
            errors.append({"step": "recommend", "type": "EMPTY_CITY",
                           "message": f"시도 {attempt}: 추천 도시가 비어 있습니다"})
            if attempt == 2:
                return None
            continue

        data["_provider"] = result.provider
        data["_model"] = result.model
        return data
    return None


# ── 2단계: 맛집 검색 (지도 API) ─────────────────────────────────────────
def step_search_places(chain: Chain, cities: list[str], n_spots: int,
                       errors: list[dict]) -> dict[str, list[dict]]:
    """지역별 맛집. **실패해도 예외를 올리지 않는다** — 빈 목록으로 다음 단계에 넘긴다.

    과제 요구: "검색 결과가 0건이면 프로그램이 중단되지 않아야 하며,
    '데이터 없음' 상태로 다음 단계(리포트 생성)로 진행한다."
    """
    found: dict[str, list[dict]] = {}
    for city in cities:
        query = f"{city} 맛집"
        try:
            result = chain.run("place_search", "search", query, n_spots)
        except ProviderError as e:
            errors.append({"step": "place_search", "city": city,
                           "type": "PROVIDER_ERROR", "message": str(e)})
            found[city] = []
            log("2/3", f"{city}: 검색 실패 — '데이터 없음'으로 계속합니다", R)
            continue

        items = [{"name": p.name, "address": p.address, "category": p.category,
                  "url": p.url, "lat": p.lat, "lng": p.lng,
                  "source": result.provider} for p in result.places]
        if not items:
            errors.append({"step": "place_search", "city": city,
                           "type": "EMPTY_RESULT", "message": f"0 results for query={query!r}"})
            log("2/3", f"{city}: 검색 결과 0건 — '데이터 없음'으로 계속합니다", Y)
        else:
            log("2/3", f"{city}: {len(items)}곳 ({result.provider})", G)
        found[city] = items
    return found


# ── 3단계: 최종 리포트 (LLM → Markdown) ─────────────────────────────────
def report_prompt(travel_date: str, rec: dict, by_city: dict[str, list[dict]]) -> str:
    lines = [
        f"아래 자료로 **{travel_date} 국내 여행 리포트**를 마크다운으로 작성하세요.",
        "",
        "## 자료",
        f"- 추천 지역: {', '.join(rec['recommended_cities'])}",
        f"- 날씨(추정): {rec['weather']}",
        f"- 행사(추정): {', '.join(rec['events']) if rec['events'] else '없음'}",
        f"- 추천 이유: {rec['reason']}",
        "",
        "### 검색된 맛집 — **이 목록에 있는 가게만 언급할 수 있습니다**",
    ]
    for city, items in by_city.items():
        lines.append(f"[{city}]")
        if not items:
            lines.append("  (검색 결과 없음)")
            continue
        for p in items:
            lines.append(f"  - {p['name']} | {p['address']} | {p['category']}")

    lines += [
        "",
        "## 작성 규칙",
        "1. 아래 순서와 제목을 그대로 씁니다.",
        "   `## 추천 지역` `## 추천 이유` `## 날씨 요약` `## 행사·축제` `## 맛집 추천` `## 1일 일정 제안`",
        "2. **맛집 추천** 섹션은 위 목록의 가게만 씁니다. "
        "   목록에 없는 가게를 만들어 내지 마세요. 형식은 `- **가게이름** — 주소 (카테고리)`",
        "3. 검색 결과가 없는 지역은 맛집 항목에 `- 데이터 없음 (장소 검색 결과 0건)` 이라고 씁니다.",
        "4. **날씨와 행사에는 반드시 '(추정)' 을 붙입니다.** 확정 정보가 아닙니다.",
        "5. 1일 일정은 오전/오후/저녁 수준으로 간단히.",
        "6. 마크다운 본문만 출력하세요. 코드블록으로 감싸지 마세요.",
    ]
    return "\n".join(lines)


def step_report(chain: Chain, travel_date: str, rec: dict,
                by_city: dict[str, list[dict]], errors: list[dict]) -> tuple[str, str | None]:
    try:
        result = chain.run("report", "complete",
                           report_prompt(travel_date, rec, by_city), max_tokens=2000)
    except ProviderError as e:
        errors.append({"step": "report", "type": "PROVIDER_ERROR", "message": str(e)})
        return fallback_report(travel_date, rec, by_city), None

    text = result.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.lstrip().startswith("markdown"):
            text = text.lstrip()[8:]
    return text.strip(), result.provider


def fallback_report(travel_date: str, rec: dict, by_city: dict[str, list[dict]]) -> str:
    """LLM이 죽어도 리포트는 나온다. 자료를 그대로 정리한 최소 버전."""
    out = [f"# {travel_date} 국내 여행 추천 리포트", "",
           "> ⚠️ LLM 호출에 실패해 자료를 그대로 정리한 최소 리포트입니다.", "",
           "## 추천 지역", ""]
    out += [f"- {c}" for c in rec["recommended_cities"]]
    out += ["", "## 추천 이유", "", rec["reason"] or "(없음)",
            "", "## 날씨 요약", "", f"{rec['weather'] or '(없음)'} (추정)",
            "", "## 행사·축제", ""]
    out += [f"- {e} (추정)" for e in rec["events"]] or ["- (없음)"]
    out += ["", "## 맛집 추천", ""]
    for city, items in by_city.items():
        out.append(f"### {city}")
        out += ([f"- **{p['name']}** — {p['address']} ({p['category']})" for p in items]
                or ["- 데이터 없음 (장소 검색 결과 0건)"])
        out.append("")
    return "\n".join(out)
