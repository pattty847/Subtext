import tempfile
import unittest
from pathlib import Path

from src.youtube_resolver import SearchResult, read_track_titles, write_resolution_files


class YoutubeResolverTests(unittest.TestCase):
    def test_read_track_titles_skips_blanks_and_comments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "crate.txt"
            path.write_text(
                "\n# Morpher crate\nChase & Status - Baddadan\n\nTyla - Water\n",
                encoding="utf-8",
            )

            titles = read_track_titles(path)

        self.assertEqual(titles, ["Chase & Status - Baddadan", "Tyla - Water"])

    def test_write_resolution_files_creates_review_tsv_jsonl_and_url_list(self):
        results = [
            SearchResult(
                query="Chase & Status - Baddadan",
                found=True,
                title="CHASE & STATUS - Baddadan ft. IRAH",
                uploader="Chase & Status",
                url="https://www.youtube.com/watch?v=abc123",
                duration=178,
                error="",
            ),
            SearchResult(
                query="Missing Track",
                found=False,
                title="",
                uploader="",
                url="",
                duration=None,
                error="No result found",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "morpher_demo_crate"
            output_paths = write_resolution_files(results, prefix)
            tsv_text = output_paths["tsv"].read_text(encoding="utf-8")
            url_text = output_paths["urls"].read_text(encoding="utf-8")
            jsonl_text = output_paths["jsonl"].read_text(encoding="utf-8")

        self.assertIn("query\tfound\ttitle\tuploader\tduration\turl\terror", tsv_text)
        self.assertIn("Chase & Status - Baddadan\ttrue", tsv_text)
        self.assertEqual(url_text, "https://www.youtube.com/watch?v=abc123\n")
        self.assertIn('"query": "Missing Track"', jsonl_text)
        self.assertIn('"found": false', jsonl_text)


if __name__ == "__main__":
    unittest.main()
