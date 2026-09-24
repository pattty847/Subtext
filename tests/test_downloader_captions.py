import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.core.downloader import UniversalDownloader


class DownloaderCaptionSourceTests(unittest.TestCase):
    def test_parse_caption_text_cleans_x_word_timing_tags(self):
        with TemporaryDirectory() as temp_dir:
            caption_path = Path(temp_dir) / "x-caption.vtt"
            caption_path.write_text(
                "\n".join(
                    [
                        "WEBVTT",
                        "",
                        "00:00:00.000 --> 00:00:02.000",
                        "<X-word-ms ms=200 index=1>I'm thrilled to report that after 35 years,</X-word-ms>",
                        "",
                        "00:00:02.000 --> 00:00:04.000",
                        "<X-word-ms ms=339 index=2>on July 4th we will end the subsidies.</X-word-ms>",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                UniversalDownloader().parse_caption_text(caption_path),
                "[00:00:00] I'm thrilled to report that after 35 years,\n"
                "[00:00:02] on July 4th we will end the subsidies.",
            )

    def test_caption_sources_try_anonymous_before_browser_cookies(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                UniversalDownloader.youtube_caption_cookie_sources(True),
                [None, "chrome", "brave", "firefox", "edge", "safari"],
            )

    def test_caption_sources_keep_configured_browser_after_anonymous(self):
        with patch.dict(os.environ, {"TRANSCRIPTAI_YT_BROWSER": "chrome"}, clear=True):
            self.assertEqual(
                UniversalDownloader.youtube_caption_cookie_sources(True),
                [None, "chrome"],
            )

    def test_caption_sources_can_disable_browser_cookie_attempts(self):
        with patch.dict(os.environ, {"TRANSCRIPTAI_YT_BROWSER": "chrome"}, clear=True):
            self.assertEqual(
                UniversalDownloader.youtube_caption_cookie_sources(False),
                [None],
            )

    def test_general_cookie_browser_prefers_subtext_setting(self):
        with patch.dict(os.environ, {"SUBTEXT_COOKIE_BROWSER": "firefox"}, clear=True):
            self.assertEqual(
                UniversalDownloader.browser_cookie_sources(True),
                [None, "firefox"],
            )

    def test_find_recent_output_returns_newest_created_file(self):
        with TemporaryDirectory() as temp_dir:
            download_dir = Path(temp_dir)
            before = download_dir / "before.mp4"
            before.write_bytes(b"before")
            before_files = {before.resolve()}

            older = download_dir / "older.webm"
            older.write_bytes(b"older")
            newer = download_dir / "newer.mp4"
            newer.write_bytes(b"newer")

            self.assertEqual(
                UniversalDownloader._find_recent_output(download_dir, before_files),
                newer,
            )

    def test_cookie_source_unavailable_errors_are_detected(self):
        self.assertTrue(
            UniversalDownloader._is_cookie_source_unavailable_error(
                Exception('could not find edge cookies database in "/tmp/Edge"')
            )
        )
        self.assertTrue(
            UniversalDownloader._is_cookie_source_unavailable_error(
                PermissionError("[Errno 1] Operation not permitted: 'Cookies.binarycookies'")
            )
        )


if __name__ == "__main__":
    unittest.main()
