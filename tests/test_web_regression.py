"""A1-1·A1-2 통합 뒤에도 A1-3의 핵심 기능이 유지되는지 확인한다."""

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import chat  # noqa: E402
import travel  # noqa: E402


class WebRegressionTest(unittest.TestCase):
    def test_guide_mode_never_calls_llm(self) -> None:
        result = chat.handle(
            {
                "utterance": "My flight is delayed. Which train can I take?",
                "delayed": True,
                "event_fired": True,
            }
        )

        self.assertEqual(result["mode"], "guide")
        self.assertEqual(result["llm_calls"], 0)
        self.assertEqual(result["generator"], "결정론 템플릿 (LLM 없음)")
        self.assertEqual(len(result["options"]), 2)
        self.assertEqual(result["grounding"]["verdict"], "pass")

    def test_input_errors_are_still_explicit(self) -> None:
        self.assertEqual(chat.handle({"utterance": ""})["error"], "EMPTY_INPUT")
        self.assertEqual(
            travel.handle({"date": "2026-02-30", "cities": 1})["error"],
            "BAD_DATE",
        )

    def test_travel_rejects_bad_types_without_server_error(self) -> None:
        # 수정 전: "abc"는 int() 예외로 500, 5는 조용히 2로 바뀌었다.
        for cities in ("abc", "2", 0, 5, True, None, 1.5):
            result = travel.handle({"date": "2026-10-01", "cities": cities})
            self.assertEqual(result.get("error"), "BAD_CITIES", cities)
        self.assertEqual(travel.handle(["not", "object"])["error"], "BAD_JSON")
        self.assertEqual(travel.handle({"date": 20261001, "cities": 1})["error"], "BAD_DATE")

    def test_fallback_report_keeps_all_six_sections(self) -> None:
        rec = {"recommended_cities": ["강릉", "제주"], "weather": "맑음",
               "events": [], "reason": "가을 여행"}
        by_city = {"강릉": [{"name": "테스트식당", "address": "강릉시", "category": "한식"}],
                   "제주": []}
        md = travel.fallback("2026-10-01", rec, by_city)
        for title in travel.SECTIONS:
            self.assertIn(f"## {title}", md)
        self.assertEqual(len(travel.SECTIONS), 6)
        # 근거 검사가 맛집 섹션을 찾을 수 있어야 한다
        import travel_grounding
        claims = travel_grounding.extract_place_claims(md)
        self.assertEqual([c.value for c in claims], ["테스트식당"])

    def test_frontend_does_not_call_zero_checks_a_pass(self) -> None:
        javascript = (ROOT / "js" / "common.js").read_text(encoding="utf-8")
        self.assertIn("Nothing to check", javascript)

    def test_bad_llm_base_url_is_a_provider_error_not_a_crash(self) -> None:
        # 배포 500 ValueError 가설: 스킴 없는 LLM_BASE_URL은 Request() 생성에서 ValueError를 냈다.
        import providers
        bad = providers.OpenAILLM("dummy-key", "gpt-4o-mini", "not-a-url")
        with self.assertRaises(providers.ProviderError):
            bad.complete("hi", max_tokens=5)

    def test_chat_failure_is_not_labelled_as_ai_success(self) -> None:
        import providers
        original = chat.llm
        chat.llm = lambda: providers.Chain(
            members=[providers.OpenAILLM("dummy-key", "gpt-4o-mini", "not-a-url")])
        try:
            result = chat.handle({"utterance": "Hi! Any tip for my first evening in Seoul?"})
        finally:
            chat.llm = original
        self.assertEqual(result["mode"], "companion")
        self.assertFalse(result["ai_generated"])
        self.assertEqual(result["generator"], "고정 안내 (AI 호출 실패)")

    def test_empty_model_env_uses_defaults(self) -> None:
        # 배포에서 Gemini 404 → 빈 GEMINI_MODEL이면 URL이 models/:generateContent가 된다(가설).
        import os
        import providers
        saved = {k: os.environ.get(k) for k in ("GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY",
                                                 "LLM_MODEL", "LLM_BASE_URL")}
        os.environ.update({"GEMINI_API_KEY": "x", "GEMINI_MODEL": "", "OPENAI_API_KEY": "y",
                           "LLM_MODEL": "", "LLM_BASE_URL": ""})
        try:
            gemini, openai = providers.llm().members[:2]
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.assertEqual(gemini.model, "gemini-2.5-flash")
        self.assertEqual(openai.model, "gpt-4o-mini")
        self.assertEqual(openai.base, "https://api.openai.com/v1")

    def test_frontend_pages_menu_and_api_routes(self) -> None:
        pages = ("index.html", "chat.html", "trip.html", "about.html")
        for page in pages:
            html = (ROOT / page).read_text(encoding="utf-8")
            for link in ("/chat.html", "/trip.html", "/about.html"):
                self.assertIn(f'href="{link}"', html, page)
        js = "".join((ROOT / "js" / f).read_text(encoding="utf-8")
                     for f in ("common.js", "chat.js", "trip.js"))
        for route in ("/api/chat", "/api/travel"):
            self.assertIn(route, js)
        rules = (ROOT / ".vercelignore").read_text(encoding="utf-8")
        for page in pages:
            self.assertIn(f"!{page}", rules)

    def test_chat_prompt_uses_history_and_trip_context(self) -> None:
        history = chat.clean_history([{"role": "user", "text": "hey"},
                                      {"role": "mate", "text": "Hey! Welcome."},
                                      {"role": "hacker", "text": "ignored"}, "bad"])
        self.assertEqual(len(history), 2)
        prompt = chat.build_prompt("where to eat?", history, "Trip date: 2026-10-03")
        self.assertIn("Mate: Hey! Welcome.", prompt)
        self.assertIn("Trip date: 2026-10-03", prompt)
        self.assertNotIn("mom", prompt)          # 고정 기억을 매 턴 주입하지 않는다

    def test_vercel_uses_official_python_detection_and_excludes_tasks(self) -> None:
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        function_config = config["functions"]["api/*.py"]

        self.assertNotIn("runtime", function_config)
        self.assertEqual(function_config["maxDuration"], 60)
        self.assertEqual((ROOT / ".python-version").read_text().strip(), "3.12")

        deployment_rules = (ROOT / ".vercelignore").read_text(encoding="utf-8")
        self.assertIn("/*", deployment_rules)
        self.assertNotIn("!tasks", deployment_rules)


if __name__ == "__main__":
    unittest.main()
