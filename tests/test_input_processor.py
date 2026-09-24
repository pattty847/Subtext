import unittest

from src.core.input_processor import InputProcessor


class InputProcessorUrlListTests(unittest.TestCase):
    def test_parse_url_list_accepts_single_url(self):
        self.assertEqual(
            InputProcessor.parse_url_list("https://example.com/video"),
            ["https://example.com/video"],
        )

    def test_parse_url_list_accepts_common_batch_separators(self):
        text = (
            "https://example.com/one, https://example.com/two\n"
            "https://example.com/three; https://example.com/four"
        )

        self.assertEqual(
            InputProcessor.parse_url_list(text),
            [
                "https://example.com/one",
                "https://example.com/two",
                "https://example.com/three",
                "https://example.com/four",
            ],
        )

    def test_parse_url_list_ignores_invalid_fragments(self):
        text = "watch these: nope https://example.com/real and not-a-url"

        self.assertEqual(
            InputProcessor.parse_url_list(text),
            ["https://example.com/real"],
        )

    def test_parse_url_list_removes_duplicates_preserving_order(self):
        text = "https://example.com/a\nhttps://example.com/b\nhttps://example.com/a"

        self.assertEqual(
            InputProcessor.parse_url_list(text),
            ["https://example.com/a", "https://example.com/b"],
        )


if __name__ == "__main__":
    unittest.main()
