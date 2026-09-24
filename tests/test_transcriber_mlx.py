import asyncio
import threading
import unittest
from pathlib import Path
from unittest import mock

from src.core import transcriber as transcriber_module
from src.core.transcriber import WhisperTranscriber, resolve_mlx_repo


class MLXTranscriberTests(unittest.TestCase):
    def test_resolve_mlx_repo_maps_short_names(self):
        self.assertEqual(resolve_mlx_repo("large-v3-turbo"), "mlx-community/whisper-large-v3-turbo")
        self.assertEqual(resolve_mlx_repo("small.en"), "mlx-community/whisper-small.en-mlx")
        self.assertEqual(resolve_mlx_repo("me/custom"), "me/custom")

    @unittest.skipUnless(transcriber_module.mlx_available(), "mlx-whisper not installed")
    def test_every_mlx_call_runs_on_one_thread(self):
        # MLX aborts the process when weights created on one thread are used on
        # another ("There is no Stream(gpu, 1) in current thread").
        seen: set[int] = set()

        class FakeHolder:
            model = None
            model_path = None

            @classmethod
            def get_model(cls, path, dtype):
                seen.add(threading.get_ident())
                cls.model = object()
                return cls.model

        fake_whisper = mock.Mock()
        fake_whisper.transcribe.side_effect = lambda *a, **k: (
            seen.add(threading.get_ident()) or {"segments": [{"text": "gamma"}]}
        )
        fake_mx = mock.Mock()
        fake_mx.clear_cache.side_effect = lambda: seen.add(threading.get_ident())

        with mock.patch.object(transcriber_module, "MLXModelHolder", FakeHolder), \
             mock.patch.object(transcriber_module, "mlx_whisper", fake_whisper), \
             mock.patch.object(transcriber_module, "mx", fake_mx):
            transcriber = WhisperTranscriber(model_name="tiny", backend="mlx")
            transcriber._ensure_ffmpeg_available = lambda: None
            transcriber._get_audio_duration = lambda _path: 1.0

            async def run():
                for _ in range(3):
                    self.assertEqual(await transcriber.transcribe(Path("clip.mp3")), "gamma")
                await asyncio.to_thread(transcriber.unload_model)

            asyncio.run(run())

        self.assertIsNone(transcriber.model)
        self.assertEqual(len(seen), 1)
        self.assertNotIn(threading.get_ident(), seen)


if __name__ == "__main__":
    unittest.main()
