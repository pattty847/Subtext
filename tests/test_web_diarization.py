import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault('SUBTEXT_SERVER_KEY', 'test')
from fastapi.testclient import TestClient
from src.web.server import app, ServiceConfig


class FakeTranscriber:
    def get_audio_duration(self, path: Path) -> float:
        return 1

    async def transcribe_stream(self, path: Path, progress_callback=None):
        yield 'Plain transcript'

    async def transcribe(self, path: Path) -> str:
        return 'Plain transcript'


class WebDiarizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.downloader = SimpleNamespace(download=AsyncMock(side_effect=self.download), is_youtube_url=lambda _: True, download_youtube_captions=AsyncMock(return_value=('Available captions', root/'captions.vtt')))
        self.service = SimpleNamespace(_lock=asyncio.Lock(), _touch_transcribe=lambda: None, transcriber=FakeTranscriber(), downloader=self.downloader, config=SimpleNamespace())
        self.old_service = getattr(app.state, 'service', None)
        self.old_config = getattr(app.state, 'config', None)
        app.state.service = self.service
        app.state.config = ServiceConfig()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.state.service = self.old_service
        app.state.config = self.old_config
        self.client.close()
        self.temporary.cleanup()

    async def download(self, url: str, **kwargs) -> Path:
        path = Path(self.temporary.name)/'audio.wav'
        path.write_bytes(b'fake audio')
        return path

    def post(self, data=None, files=None):
        return self.client.post('/transcribe/stream', data=data, files=files, headers={'X-Subtext-Key': 'test'})

    def test_toggle_on_uses_audio_not_captions_and_preserves_speaker_text(self) -> None:
        labeled = AsyncMock(return_value='[00:00.00] Person 1: Hi\n[00:01.00] Person 2: Hello')
        with patch('src.web.server.diarization.ensure_available'), patch('src.web.server.diarization.transcribe_labeled', labeled), patch('src.web.server.validate_media_url', side_effect=lambda u: u):
            result = self.post({'url': 'https://example.com/video', 'identify_speakers': 'true'})
        self.assertEqual(result.status_code, 200)
        self.assertIn('Person 1', result.text)
        self.assertIn('Person 2', result.text)
        self.downloader.download_youtube_captions.assert_not_awaited()
        self.downloader.download.assert_awaited_once()
        labeled.assert_awaited_once()

    def test_toggle_off_keeps_captions_fast_path(self) -> None:
        with patch('src.web.server.validate_media_url', side_effect=lambda u: u), patch('src.web.server._web_youtube_captions_enabled', return_value=True), patch('src.web.server.diarization.transcribe_labeled', new=AsyncMock()) as labeled:
            result = self.post({'url': 'https://example.com/video'})
        self.assertIn('Available captions', result.text)
        self.downloader.download.assert_not_awaited()
        labeled.assert_not_awaited()

    def test_missing_install_is_reported_before_downloading(self) -> None:
        with patch('src.web.server.diarization.ensure_available', side_effect=RuntimeError('Install NVIDIA')):
            result = self.post({'url': 'https://example.com/video', 'identify_speakers': 'true'})
        self.assertEqual(result.status_code, 503)
        self.downloader.download.assert_not_awaited()

    def test_batch_labels_each_recording_and_keeps_source_sections(self) -> None:
        labeled = AsyncMock(return_value='Person 1: First voice\nPerson 2: Second voice')
        with patch('src.web.server.diarization.ensure_available'), patch('src.web.server.diarization.transcribe_labeled', labeled), patch('src.web.server.validate_media_url', side_effect=lambda u: u):
            result = self.post({'url': 'https://example.com/one\nhttps://example.com/two', 'identify_speakers': 'true'})
        self.assertEqual(labeled.await_count, 2)
        self.assertIn('## 1.', result.text)
        self.assertIn('## 2.', result.text)
        self.downloader.download_youtube_captions.assert_not_awaited()

    def test_json_upload_endpoint_passes_the_optional_flag(self) -> None:
        for enabled in [False, True]:
            self.service.transcribe_upload = AsyncMock(return_value={'text': 'Example', 'duration': 1, 'latency': 1})
            with self.subTest(enabled=enabled), patch('src.web.server.diarization.ensure_available'):
                result = self.client.post('/api/transcribe', data={'identify_speakers': str(enabled).lower()}, files={'file': ('sample.wav', b'audio', 'audio/wav')}, headers={'X-Subtext-Key': 'test'})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(self.service.transcribe_upload.await_args.args[1:], (True,) if enabled else ())

    def test_upload_supports_both_modes(self) -> None:
        for enabled in [False, True]:
            with self.subTest(enabled=enabled), patch('src.web.server.diarization.ensure_available'), patch('src.web.server.diarization.transcribe_labeled', new=AsyncMock(return_value='Person 1: Local audio')) as labeled:
                result = self.post({'identify_speakers': str(enabled).lower()}, {'file': ('sample.wav', b'fake audio', 'audio/wav')})
                self.assertIn('Person 1' if enabled else 'Plain transcript', result.text)
                self.assertEqual(labeled.await_count, int(enabled))


if __name__ == '__main__':
    unittest.main()
