import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.core.diarization import SpeakerTurn, label_words, parse_rttm
from src.core.transcriber import WhisperTranscriber


class DiarizationTests(unittest.TestCase):
    def test_returning_speaker_keeps_identity(self) -> None:
        turns = [SpeakerTurn(0, 1, 'speaker_a'), SpeakerTurn(1, 2, 'speaker_b'), SpeakerTurn(2, 3, 'speaker_a')]
        words = [{'start': i + .1, 'end': i + .8, 'text': text} for i, text in enumerate(['Hello.', 'Hi.', 'Again.'])]
        text = label_words(words, turns)
        self.assertIn('Person 1: Hello.', text)
        self.assertIn('Person 2: Hi.', text)
        self.assertIn('Person 1: Again.', text)

    def test_overlap_and_missing_activity_are_not_confidently_assigned(self) -> None:
        turns = [SpeakerTurn(0, 2, 'a'), SpeakerTurn(1, 2, 'b')]
        result = label_words([{'start': 1.1, 'end': 1.8, 'text': 'Mixed'}, {'start': 3, 'end': 4, 'text': 'Unknown'}], turns)
        self.assertIn('Unclear (Person 1 / Person 2 overlapping): Mixed', result)
        self.assertIn('Unattributed: Unknown', result)

    def test_boundary_uncertainty_differs_from_simultaneous_speech(self) -> None:
        result = label_words([{'start': .8, 'end': 1.2, 'text': 'Transition'}], [SpeakerTurn(0, 1, 'a'), SpeakerTurn(1, 2, 'b')])
        self.assertIn('boundary', result)
        self.assertNotIn('overlapping):', result)

    def test_zero_duration_word_is_retained_as_unattributed(self) -> None:
        result = label_words([{'start': 0, 'end': 0, 'text': 'Keep this'}], [SpeakerTurn(0, 1, 'a')])
        self.assertIn('Unattributed: Keep this', result)

    def test_rttm_is_sorted_and_invalid_times_are_rejected(self) -> None:
        turns = parse_rttm('SPEAKER x 1 2 1 <NA> <NA> b <NA> <NA>\nSPEAKER x 1 0 1 <NA> <NA> a <NA> <NA>')
        self.assertEqual(turns[0].speaker, 'a')
        for value in ['bad', 'SPEAKER x 1 nan 1 <NA> <NA> a', 'SPEAKER x 1 0 -1 <NA> <NA> a']:
            with self.assertRaises(ValueError):
                parse_rttm(value)

    def test_faster_whisper_word_timestamps_requested_without_changing_plain_defaults(self) -> None:
        word = SimpleNamespace(start=0, end=1, word=' Hello')
        segment = SimpleNamespace(words=[word])
        model = SimpleNamespace(transcribe=Mock(return_value=(iter([segment]), object())))
        transcriber = WhisperTranscriber(backend='faster-whisper', device='cpu')
        transcriber.model = model
        transcriber._ensure_ffmpeg_available = lambda: None
        self.assertEqual(asyncio.run(transcriber.transcribe_words(Path('sample.wav'))), [{'start': 0, 'end': 1, 'text': ' Hello'}])
        self.assertTrue(model.transcribe.call_args.kwargs['word_timestamps'])


class DiarizationLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_reaps_native_child(self) -> None:
        import sys
        from src.core import diarization
        original_spawn = asyncio.create_subprocess_exec
        started = asyncio.Event()
        children = []

        async def spawn(*args, **kwargs):
            process = await original_spawn(*args, **kwargs)
            children.append(process)
            started.set()
            return process

        with patch.object(diarization.asyncio, 'create_subprocess_exec', side_effect=spawn):
            task = asyncio.create_task(diarization._run(sys.executable, '-c', 'import time; time.sleep(60)'))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIsNotNone(children[0].returncode)

    async def test_native_failure_cleans_temporary_audio(self) -> None:
        from tempfile import TemporaryDirectory
        from unittest.mock import AsyncMock, Mock
        from src.core import diarization
        from src.config.paths import ProjectPaths
        transcriber = SimpleNamespace(unload_model=Mock(), transcribe_words=AsyncMock())
        with TemporaryDirectory() as directory:
            with patch.object(ProjectPaths, 'RUNTIME_DIR', Path(directory)), patch.object(ProjectPaths, 'ensure_directories'), patch.object(diarization, 'ensure_available', return_value=(Path('nemo-speech'), Path('model.gguf'))), patch.object(diarization, '_run', new=AsyncMock(side_effect=RuntimeError('conversion failed'))):
                with self.assertRaisesRegex(RuntimeError, 'conversion failed'):
                    await diarization.transcribe_labeled(Path('clip.wav'), transcriber)
            self.assertEqual(list(Path(directory).iterdir()), [])
        transcriber.transcribe_words.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
