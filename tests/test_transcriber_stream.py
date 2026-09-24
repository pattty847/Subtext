import asyncio
import unittest
from pathlib import Path

from src.core.transcriber import WhisperTranscriber


class FakeSegment:
    def __init__(self, text: str):
        self.text = text


class FakeFasterWhisperModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return iter([FakeSegment("first line"), FakeSegment("second line")]), object()


class TestableWhisperTranscriber(WhisperTranscriber):
    def _ensure_ffmpeg_available(self) -> None:
        return None

    def _get_audio_duration(self, audio_path: Path) -> float:
        return 1.0


class TranscriberStreamTests(unittest.TestCase):
    def test_faster_whisper_stream_uses_dense_speech_safe_defaults(self):
        fake_model = FakeFasterWhisperModel()
        transcriber = TestableWhisperTranscriber(
            model_name="tiny.en",
            device="cpu",
            backend="faster-whisper",
        )
        transcriber.model = fake_model

        async def collect_chunks():
            chunks = []
            async for chunk in transcriber.transcribe_stream(Path("sample.mp3")):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(collect_chunks())

        self.assertEqual(chunks, ["first line", "second line"])
        self.assertEqual(fake_model.calls[0][0], "sample.mp3")
        options = fake_model.calls[0][1]
        self.assertEqual(options["beam_size"], 5)
        self.assertFalse(options["vad_filter"])
        self.assertTrue(options["condition_on_previous_text"])


if __name__ == "__main__":
    unittest.main()
