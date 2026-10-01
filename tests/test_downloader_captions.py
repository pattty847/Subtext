import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.core.downloader import UniversalDownloader


class DownloaderCaptionSourceTests(unittest.TestCase):
    def test_download_youtube_captions_reuses_existing_vtt_for_same_video(self):
        class FakeYoutubeDL:
            def __enter__(self):
                return self

            def __exit__(self, _type, _value, _traceback):
                return False

            def extract_info(self, _url, download):
                assert download
                return {"id": "sample123"}

        with TemporaryDirectory() as temp_dir:
            downloader = UniversalDownloader(output_dir=Path(temp_dir))
            downloader.transcripts_dir.mkdir(parents=True, exist_ok=True)
            caption_path = downloader.transcripts_dir / "Existing_Title_[sample123].en.vtt"
            caption_path.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello again.\n",
                encoding="utf-8",
            )

            with patch("src.core.downloader.yt_dlp.YoutubeDL", return_value=FakeYoutubeDL()):
                text, output_path = asyncio.run(
                    downloader.download_youtube_captions(
                        "https://www.youtube.com/watch?v=sample123",
                        use_browser_cookies=False,
                        max_retries=0,
                    )
                )

            self.assertEqual(text, "[00:00:01] Hello again.")
            self.assertEqual(output_path.read_text(encoding="utf-8"), text)

    def test_parse_caption_text_merges_rolling_youtube_cues(self):
        with TemporaryDirectory() as temp_dir:
            caption_path = Path(temp_dir) / "rolling.vtt"
            caption_path.write_text(
                "\n".join(
                    [
                        "WEBVTT", "",
                        "00:00:01.000 --> 00:00:02.000", "<c>Hello</c>", "",
                        "00:00:02.000 --> 00:00:03.000", "Hello there", "",
                        "00:00:03.000 --> 00:00:04.000", "there, my friend.", "",
                        "00:00:04.000 --> 00:00:05.000", "there, my friend.", "",
                        "00:00:07.000 --> 00:00:08.000", "Hello there", "",
                        "00:00:08.000 --> 00:00:09.000", "Hello there again.",
                    ]
                ),
                encoding="utf-8",
            )

            downloader = UniversalDownloader()
            expected = "[00:00:01] Hello there, my friend.\n[00:00:07] Hello there again."
            self.assertEqual(downloader.parse_caption_text(caption_path), expected)
            self.assertEqual(
                downloader.parse_caption_text(caption_path, include_timestamps=False),
                "Hello there, my friend.\nHello there again.",
            )

    def test_parse_caption_text_preserves_speaker_changes(self):
        with TemporaryDirectory() as temp_dir:
            caption_path = Path(temp_dir) / "speakers.vtt"
            caption_path.write_text(
                "\n".join(
                    [
                        "WEBVTT", "",
                        "00:00:01.000 --> 00:00:02.000", "<v Alex>Hello", "",
                        "00:00:02.000 --> 00:00:03.000", "Hello there", "",
                        "00:00:03.000 --> 00:00:04.000", "<v Sam>There you are.",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                UniversalDownloader().parse_caption_text(caption_path),
                "[00:00:01] Alex: Hello there\n[00:00:03] Sam: There you are.",
            )

    def test_parse_caption_text_keeps_periodic_timestamps_in_long_roll(self):
        with TemporaryDirectory() as temp_dir:
            caption_path = Path(temp_dir) / "long-roll.srt"
            caption_path.write_text(
                "\n".join(
                    [
                        "1", "00:00:00,000 --> 00:00:10,000", "one two", "",
                        "2", "00:00:10,000 --> 00:00:20,000", "two three", "",
                        "3", "00:00:20,000 --> 00:00:30,000", "three four", "",
                        "4", "00:00:21,000 --> 00:00:31,000", "four five",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                UniversalDownloader().parse_caption_text(caption_path),
                "[00:00:00] one two three\n[00:00:20] four five",
            )

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
