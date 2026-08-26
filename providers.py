"""API 제공자 — 주 제공자가 죽으면 보조로 자동 전환한다.

    from providers import llm, places
    text  = llm().complete("...")          # Gemini → 실패 시 OpenAI
    spots = places().search("동대구 맛집")   # Kakao  → 실패 시 Naver

설계 원칙
  · **어느 제공자가 답했는지 반드시 기록한다.** 리포트의 '근거 출처'에 들어가야 하고,
    말없이 다른 제공자로 바뀌면 결과가 왜 달라졌는지 추적할 수 없다.
  · 전환은 **호출 가능성 문제일 때만** 한다(인증·쿼터·네트워크·5xx).
    빈 결과(0건)는 실패가 아니다 — 과제 요구대로 '데이터 없음'으로 다음 단계에 넘긴다.
  · 키가 하나도 없으면 즉시 종료하고 설정 방법을 안내한다(A1-2 §6 최소 정책).
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# ── SSL ────────────────────────────────────────────────────────────────
# macOS python.org 빌드는 시스템 키체인을 보지 않는다. certifi가 있으면 그것을 쓴다.
def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


CTX = _ssl_context()


def load_env(path: Path | None = None) -> None:
    path = path or Path(__file__).resolve().parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class ProviderError(RuntimeError):
    """전환을 유발하는 오류. 빈 결과는 여기에 해당하지 않는다."""


def _req(url: str, *, headers: dict | None = None, body: dict | None = None,
         timeout: int = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers or {})
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        raise ProviderError(f"HTTP {e.code} · {detail}") from e
    except Exception as e:
        raise ProviderError(f"{type(e).__name__}: {e}") from e


# ── LLM ────────────────────────────────────────────────────────────────
@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


class GeminiLLM:
    name = "gemini"

    def __init__(self, key: str, model: str = "gemini-2.5-flash"):
        self.key, self.model = key, model

    def complete(self, prompt: str, *, max_tokens: int = 1024,
                 json_mode: bool = False) -> LLMResult:
        # gemini-2.5 계열은 '생각' 토큰을 maxOutputTokens에서 함께 소모한다.
        # 끄지 않으면 답이 한 글자로 잘린다(실측: 100토큰 예산이 생각으로 전부 소진됨).
        cfg = {"maxOutputTokens": max_tokens, "temperature": 0.7,
               "thinkingConfig": {"thinkingBudget": 0}}
        if json_mode:
            cfg["responseMimeType"] = "application/json"
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent?key={urllib.parse.quote(self.key)}")
        out = _req(url, body=body)
        try:
            text = out["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ProviderError(f"응답 형식이 예상과 다르다: {str(out)[:200]}") from e
        return LLMResult(text, self.name, self.model)


class OpenAILLM:
    name = "openai"

    def __init__(self, key: str, model: str = "gpt-4o-mini",
                 base_url: str = "https://api.openai.com/v1"):
        self.key, self.model, self.base = key, model, base_url.rstrip("/")

    def complete(self, prompt: str, *, max_tokens: int = 1024,
                 json_mode: bool = False) -> LLMResult:
        body = {"model": self.model, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        out = _req(f"{self.base}/chat/completions",
                   headers={"Authorization": f"Bearer {self.key}"}, body=body)
        try:
            text = out["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise ProviderError(f"응답 형식이 예상과 다르다: {str(out)[:200]}") from e
        return LLMResult(text, self.name, self.model)


# ── 장소 검색 ───────────────────────────────────────────────────────────
@dataclass
class Place:
    name: str
    address: str
    category: str = ""
    url: str = ""
    lat: float | None = None
    lng: float | None = None


@dataclass
class PlaceResult:
    places: list[Place]
    provider: str


class KakaoPlaces:
    name = "kakao"

    def __init__(self, key: str):
        self.key = key

    def search(self, query: str, size: int = 5) -> PlaceResult:
        q = urllib.parse.urlencode({"query": query, "size": size})
        out = _req(f"https://dapi.kakao.com/v2/local/search/keyword.json?{q}",
                   headers={"Authorization": f"KakaoAK {self.key}"})
        places = [
            Place(name=d.get("place_name", ""), address=d.get("road_address_name")
                  or d.get("address_name", ""), category=d.get("category_name", ""),
                  url=d.get("place_url", ""),
                  lat=float(d["y"]) if d.get("y") else None,
                  lng=float(d["x"]) if d.get("x") else None)
            for d in out.get("documents", [])
        ]
        return PlaceResult(places, self.name)


class NaverPlaces:
    name = "naver"

    def __init__(self, cid: str, secret: str):
        self.cid, self.secret = cid, secret

    @staticmethod
    def _strip(s: str) -> str:
        return s.replace("<b>", "").replace("</b>", "")

    def search(self, query: str, size: int = 5) -> PlaceResult:
        q = urllib.parse.urlencode({"query": query, "display": size})
        out = _req(f"https://openapi.naver.com/v1/search/local.json?{q}",
                   headers={"X-Naver-Client-Id": self.cid,
                            "X-Naver-Client-Secret": self.secret})
        places = []
        for d in out.get("items", []):
            # 네이버는 KATECH 좌표(mapx/mapy)를 준다. WGS84가 아니므로 그대로 쓰지 않는다.
            places.append(Place(
                name=self._strip(d.get("title", "")),
                address=d.get("roadAddress") or d.get("address", ""),
                category=d.get("category", ""), url=d.get("link", "")))
        return PlaceResult(places, self.name)


# ── 폴백 체인 ───────────────────────────────────────────────────────────
@dataclass
class Chain:
    """주 제공자 → 보조 제공자. 어떤 전환이 있었는지 errors에 남긴다."""

    members: list = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def run(self, step: str, fn_name: str, *args, **kwargs):
        if not self.members:
            raise ProviderError(
                f"{step}: 사용 가능한 제공자가 없다. .env에 키를 넣고 "
                f"python3 check_keys.py --live 로 확인하라.")
        last = None
        for i, m in enumerate(self.members):
            try:
                return getattr(m, fn_name)(*args, **kwargs)
            except ProviderError as e:
                last = e
                self.errors.append({"step": step, "provider": m.name,
                                    "type": "PROVIDER_ERROR", "message": str(e),
                                    "fell_back": i + 1 < len(self.members)})
        raise ProviderError(f"{step}: 모든 제공자 실패. 마지막 오류 — {last}")


def llm(chain: Chain | None = None) -> Chain:
    """주: Gemini · 보조: OpenAI (사용자 지정 우선순위)"""
    load_env()
    c = chain or Chain()
    if os.environ.get("GEMINI_API_KEY"):
        c.members.append(GeminiLLM(os.environ["GEMINI_API_KEY"],
                                   os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")))
    if os.environ.get("OPENAI_API_KEY"):
        c.members.append(OpenAILLM(os.environ["OPENAI_API_KEY"],
                                   os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                                   os.environ.get("LLM_BASE_URL",
                                                  "https://api.openai.com/v1")))
    return c


def places(chain: Chain | None = None) -> Chain:
    """주: Kakao · 보조: Naver (사용자 지정 우선순위)"""
    load_env()
    c = chain or Chain()
    if os.environ.get("KAKAO_REST_API_KEY"):
        c.members.append(KakaoPlaces(os.environ["KAKAO_REST_API_KEY"]))
    if os.environ.get("NAVER_CLIENT_ID") and os.environ.get("NAVER_CLIENT_SECRET"):
        c.members.append(NaverPlaces(os.environ["NAVER_CLIENT_ID"],
                                     os.environ["NAVER_CLIENT_SECRET"]))
    return c
