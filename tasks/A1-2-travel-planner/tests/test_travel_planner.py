import json
import sys
import tempfile
import unittest
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK_DIR))

import grounding
import travel_planner


class TravelPlannerTest(unittest.TestCase):
    def test_accepts_assignment_and_conventional_date_options(self):
        parser = travel_planner.build_parser()
        self.assertEqual(parser.parse_args(["-date", "2026-03-15"]).date, "2026-03-15")
        self.assertEqual(parser.parse_args(["--date", "2026-03-15"]).date, "2026-03-15")

    def test_rejects_impossible_date(self):
        with self.assertRaises(SystemExit):
            travel_planner.build_parser().parse_args(["--date", "2026-13-45"])

    def test_normalises_required_schema(self):
        data = travel_planner.normalise_recommendation({
            "recommended_city": "제주",
            "weather": "봄 날씨",
            "events": ["유채꽃 행사"],
            "reason": "야외 활동에 좋습니다.",
        }, 1)
        self.assertEqual(data["recommended_cities"], ["제주"])

    def test_rejects_missing_or_wrong_schema(self):
        with self.assertRaises(ValueError):
            travel_planner.normalise_recommendation({
                "recommended_city": "제주", "weather": "", "events": [], "reason": "이유"
            }, 1)
        with self.assertRaises(ValueError):
            travel_planner.normalise_recommendation({
                "recommended_city": "제주", "weather": "날씨", "events": "행사", "reason": "이유"
            }, 1)
        with self.assertRaises(ValueError):
            travel_planner.normalise_recommendation({
                "recommended_city": "제주", "weather": "날씨", "events": [], "reason": "이유"
            }, 1)

    def test_empty_place_list_is_recorded_without_stopping(self):
        class EmptyResult:
            places = []
            provider = "fake-map"

        class EmptyChain:
            def run(self, *args, **kwargs):
                return EmptyResult()

        errors = []
        found = travel_planner.step_search_places(EmptyChain(), ["제주"], 5, errors)
        self.assertEqual(found, {"제주": []})
        self.assertEqual(errors[0]["type"], "EMPTY_RESULT")

    def test_save_results_creates_json_and_markdown(self):
        rec = {"recommended_cities": ["제주"], "weather": "날씨",
               "events": [], "reason": "이유"}
        guard = grounding.Report(verdict=grounding.Verdict.NO_CLAIM)
        with tempfile.TemporaryDirectory() as directory:
            original = travel_planner.RESULTS
            travel_planner.RESULTS = Path(directory) / "results"
            try:
                raw, report = travel_planner.save_results(
                    "2026-03-15", rec, {"제주": []}, "# 리포트\n", [], guard)
                saved = json.loads(raw.read_text(encoding="utf-8"))
                self.assertTrue(raw.exists())
                self.assertTrue(report.exists())
                self.assertEqual(saved["errors"], [])
            finally:
                travel_planner.RESULTS = original


if __name__ == "__main__":
    unittest.main()
