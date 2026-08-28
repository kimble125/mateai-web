"""핵심 사용자 흐름을 확인하는 표준 라이브러리 테스트."""

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import prompt_manager


class PromptManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.prompts = prompt_manager.seed_prompts()

    def capture(self, function, *args) -> str:
        output = StringIO()
        with redirect_stdout(output):
            function(*args)
        return output.getvalue()

    def test_default_data_has_required_fields_and_previous_missions(self) -> None:
        self.assertEqual(len(self.prompts), 8)
        for prompt in self.prompts:
            self.assertTrue(
                {"title", "content", "category", "favorite"} <= prompt.keys()
            )

        previous_missions = [
            prompt for prompt in self.prompts if prompt["title"].startswith("[B1-")
        ]
        self.assertGreaterEqual(len(previous_missions), 3)

    def test_add_search_detail_and_favorite_flow(self) -> None:
        with patch(
            "builtins.input",
            side_effect=["평가용 프롬프트", "기억 검색 키워드", "1"],
        ):
            self.capture(prompt_manager.add_prompt, self.prompts)

        added_number = str(len(self.prompts))
        self.assertEqual(self.prompts[-1]["favorite"], False)

        with patch("builtins.input", return_value="기억 검색"):
            search_output = self.capture(prompt_manager.search_prompt, self.prompts)
        self.assertIn("평가용 프롬프트", search_output)

        with patch("builtins.input", return_value=added_number):
            detail_output = self.capture(prompt_manager.show_detail, self.prompts)
        self.assertIn("사용 횟수: 1회", detail_output)

        with patch("builtins.input", return_value=added_number):
            favorite_output = self.capture(
                prompt_manager.toggle_favorite, self.prompts
            )
        self.assertIn("즐겨찾기에 추가했습니다", favorite_output)
        self.assertTrue(self.prompts[-1]["favorite"])

    def test_save_load_and_markdown_export_are_explicit(self) -> None:
        original_directory = os.getcwd()
        with tempfile.TemporaryDirectory() as temporary_directory:
            try:
                os.chdir(temporary_directory)
                self.capture(prompt_manager.save_to_file, self.prompts)
                self.assertTrue(os.path.exists("prompts.json"))

                self.prompts.clear()
                self.capture(prompt_manager.load_from_file, self.prompts)
                self.assertEqual(len(self.prompts), 8)

                self.capture(prompt_manager.export_markdown, self.prompts)
                self.assertTrue(os.path.isdir("exports"))
                self.assertTrue(os.listdir("exports"))

                with open("prompts.json", encoding="utf-8") as file:
                    saved = json.load(file)
                self.assertEqual(saved[0]["title"], self.prompts[0]["title"])
            finally:
                os.chdir(original_directory)

    def test_invalid_menu_choice_returns_to_menu_before_exit(self) -> None:
        with patch("builtins.input", side_effect=["99", "0"]):
            output = self.capture(prompt_manager.main)

        self.assertIn("[안내] 0부터 13 사이의 번호", output)
        self.assertGreaterEqual(output.count("=== 나만의 프롬프트 관리 ==="), 2)
        self.assertIn("종료합니다.", output)


if __name__ == "__main__":
    unittest.main()
