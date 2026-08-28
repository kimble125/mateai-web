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

    def test_frontend_keeps_sections_and_api_routes(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "js" / "app.js").read_text(encoding="utf-8")

        for section in ("소개", "라이브 챗", "여행 리포트", "엔진 내부"):
            self.assertIn(section, html)
        for route in ("/api/chat", "/api/travel"):
            self.assertIn(route, javascript)

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
