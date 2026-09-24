import unittest
import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

os.environ.setdefault("SUBTEXT_SERVER_KEY", "test")

from src.web.server import (  # noqa: E402
    _batch_error_section,
    _batch_success_section,
    _batch_title_from_path,
    app,
)


class WebBatchTranscriptionTests(unittest.TestCase):
    def test_batch_success_section_marks_source_title_status_and_divider(self):
        self.assertEqual(
            _batch_success_section(
                2,
                "https://example.com/two",
                "A useful reel",
                "transcript text",
            ),
            "\n\n---\n\n## 2. A useful reel\nSource: https://example.com/two\nStatus: transcribed\n\ntranscript text\n",
        )

    def test_batch_title_from_path_uses_yt_dlp_filename_title(self):
        self.assertEqual(
            _batch_title_from_path(Path("Global_Flood_Update_[abc123].mp4")),
            "Global Flood Update",
        )

    def test_batch_error_section_includes_error_message(self):
        self.assertEqual(
            _batch_error_section(3, "https://example.com/bad", "Download failed"),
            "\n\n---\n\n## 3. https://example.com/bad\nStatus: error\n\nError: Download failed\n",
        )

    def test_transcribe_stream_batches_exact_instagram_semicolon_input(self):
        text = (
            "https://www.instagram.com/reel/DWyv8OUEYFg/?utm_source=ig_web_copy_link&igsh=NTc4MTIwNjQ2YQ==;"
            "https://www.instagram.com/reel/DXcUhLxDHAR/?utm_source=ig_web_copy_link&igsh=NTc4MTIwNjQ2YQ=="
        )

        with TemporaryDirectory() as temp_dir:
            with TestClient(app) as client:
                app.state.service = FakeBatchService(Path(temp_dir))

                response = client.post(
                    "/transcribe/stream",
                    data={"url": text},
                    headers={"x-subtext-key": "test"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertIn("Transcribing 1 of 2", response.text)
                self.assertIn("Transcribing 2 of 2", response.text)
                self.assertIn("## 1. First Instagram Reel", response.text)
                self.assertIn("## 2. Second Instagram Reel", response.text)
                self.assertEqual(len(app.state.service.downloader.calls), 2)

    def test_transcribe_stream_uses_youtube_captions_before_downloading_media(self):
        with TemporaryDirectory() as temp_dir:
            with TestClient(app) as client:
                app.state.service = FakeBatchService(Path(temp_dir))

                response = client.post(
                    "/transcribe/stream",
                    data={"url": "https://www.youtube.com/watch?v=captions"},
                    headers={"x-subtext-key": "test"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertIn("Using YouTube captions", response.text)
                self.assertIn("caption transcript", response.text)
                self.assertEqual(app.state.service.downloader.caption_calls, ["https://www.youtube.com/watch?v=captions"])
                self.assertEqual(app.state.service.downloader.caption_kwargs[0]["use_browser_cookies"], False)
                self.assertEqual(app.state.service.downloader.calls, [])

    def test_transcribe_stream_uses_browser_cookie_fallback_for_non_youtube_urls(self):
        with TemporaryDirectory() as temp_dir:
            with TestClient(app) as client:
                app.state.service = FakeBatchService(Path(temp_dir))

                response = client.post(
                    "/transcribe/stream",
                    data={"url": "https://www.instagram.com/reel/test123/"},
                    headers={"x-subtext-key": "test"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    app.state.service.downloader.calls,
                    [("https://www.instagram.com/reel/test123/", True)],
                )

    def test_transcribe_stream_uses_generic_url_captions_before_downloading_media(self):
        with TemporaryDirectory() as temp_dir:
            with TestClient(app) as client:
                app.state.service = FakeBatchService(Path(temp_dir))

                response = client.post(
                    "/transcribe/stream",
                    data={"url": "https://x.com/example/status/123/video/1"},
                    headers={"x-subtext-key": "test"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertIn("Using available captions", response.text)
                self.assertIn("x caption transcript", response.text)
                self.assertEqual(
                    app.state.service.downloader.url_caption_calls,
                    [("https://x.com/example/status/123/video/1", True)],
                )
                self.assertEqual(app.state.service.downloader.calls, [])

    def test_transcribe_stream_blocks_long_youtube_whisper_fallback(self):
        with TemporaryDirectory() as temp_dir:
            with TestClient(app) as client:
                service = FakeBatchService(Path(temp_dir))
                service.downloader.caption_error = Exception("No YouTube caption track found.")
                service.transcriber.duration = 1_500.0
                app.state.service = service

                response = client.post(
                    "/transcribe/stream",
                    data={"url": "https://www.youtube.com/watch?v=long"},
                    headers={"x-subtext-key": "test"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertIn("captions unavailable", response.text.lower())
                self.assertIn("20 minutes", response.text)
                self.assertEqual(service.transcriber.stream_calls, [])


class FakeBatchDownloader:
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.calls: list[str] = []
        self.caption_calls: list[str] = []
        self.caption_kwargs: list[dict] = []
        self.url_caption_calls: list[tuple[str, bool]] = []
        self.caption_error: Exception | None = None

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        return "youtube.com" in url or "youtu.be" in url

    async def download_youtube_captions(self, url: str, **kwargs):
        self.caption_calls.append(url)
        self.caption_kwargs.append(kwargs)
        if self.caption_error is not None:
            raise self.caption_error
        path = self.temp_dir / "Caption_Title_[captions].txt"
        path.write_text("caption transcript", encoding="utf-8")
        return "caption transcript", path

    async def download_url_captions(self, url: str, use_browser_cookies: bool = False):
        self.url_caption_calls.append((url, use_browser_cookies))
        if "x.com" not in url:
            raise Exception("No URL caption track found.")
        path = self.temp_dir / "X_Caption_Title_[x123].txt"
        path.write_text("x caption transcript", encoding="utf-8")
        return "x caption transcript", path

    async def download(self, url: str, use_browser_cookies: bool = False) -> Path:
        self.calls.append((url, use_browser_cookies))
        if "youtube" in url:
            title = "Long_YouTube_Video_[long]"
        else:
            title = "First_Instagram_Reel_[one]" if len(self.calls) == 1 else "Second_Instagram_Reel_[two]"
        path = self.temp_dir / f"{title}.mp4"
        path.write_bytes(b"fake media")
        return path


class FakeBatchTranscriber:
    def __init__(self):
        self.duration = 1.0
        self.stream_calls: list[Path] = []
        self.transcribe_calls: list[Path] = []

    def get_audio_duration(self, path: Path) -> float:
        return self.duration

    async def transcribe(self, path: Path) -> str:
        self.transcribe_calls.append(path)
        return f"transcript for {path.stem}"

    async def transcribe_stream(self, path: Path, progress_callback=None):
        self.stream_calls.append(path)
        yield f"transcript for {path.stem}"


class FakeBatchService:
    def __init__(self, temp_dir: Path):
        self._lock = asyncio.Lock()
        self.downloader = FakeBatchDownloader(temp_dir)
        self.transcriber = FakeBatchTranscriber()

    def _touch_transcribe(self) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
