"""Local NVIDIA speaker diarization and conservative transcript attribution."""
from __future__ import annotations

import asyncio
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, TYPE_CHECKING

from src.config.paths import ProjectPaths

if TYPE_CHECKING:
    from src.core.transcriber import WhisperTranscriber

RUNTIME_NAME = 'nemo-speech-0.2.0-macos-aarch64-metal'
MODEL_NAME = 'Nemotron-3-Diarization.q8_0.gguf'


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


def resource_paths() -> tuple[Path, Path]:
    root = ProjectPaths.RUNTIME_DIR / 'diarization'
    binary = Path(os.getenv('SUBTEXT_DIARIZATION_BIN') or root / 'runtime' / RUNTIME_NAME / 'bin/nemo-speech')
    model = Path(os.getenv('SUBTEXT_DIARIZATION_MODEL') or root / MODEL_NAME)
    return binary, model


def ensure_available() -> tuple[Path, Path]:
    binary, model = resource_paths()
    if not binary.is_file() or not os.access(binary, os.X_OK) or not model.is_file():
        raise RuntimeError('Speaker labeling is not installed. Run uv run python scripts/setup_diarization.py on the Mac, or turn off Identify speakers.')
    return binary, model


def parse_rttm(text: str) -> list[SpeakerTurn]:
    """Read speaker intervals, rejecting malformed output rather than guessing."""
    turns = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        fields = line.split()
        if len(fields) < 8 or fields[0] != 'SPEAKER':
            raise ValueError('NVIDIA returned invalid speaker timestamps.')
        start, duration = float(fields[3]), float(fields[4])
        if not math.isfinite(start) or not math.isfinite(duration) or start < 0 or duration <= 0:
            raise ValueError('NVIDIA returned invalid speaker timestamps.')
        turns.append(SpeakerTurn(start, start + duration, fields[7]))
    return sorted(turns, key=lambda turn: (turn.start, turn.end))


def _speaker_label(start: float, end: float, turns: list[SpeakerTurn], names: dict[str, str]) -> str:
    scores: dict[str, float] = {}
    active_turns = [turn for turn in turns if turn.start < end and turn.end > start]
    for turn in active_turns:
        overlap = max(0.0, min(end, turn.end) - max(start, turn.start))
        if overlap:
            scores[turn.speaker] = scores.get(turn.speaker, 0) + overlap
    if not scores:
        return 'Unattributed'
    ordered = sorted(scores, key=scores.get, reverse=True)
    # Do not pretend Whisper separated simultaneous voices into distinct words.
    ambiguous = [speaker for speaker in ordered if scores[speaker] >= scores[ordered[0]] * 0.25]
    if len(ambiguous) > 1:
        simultaneous = any(
            left.speaker != right.speaker
            and max(start, left.start, right.start) < min(end, left.end, right.end)
            for index, left in enumerate(active_turns) for right in active_turns[index + 1:]
            if left.speaker in ambiguous and right.speaker in ambiguous
        )
        reason = ' overlapping' if simultaneous else ' boundary'
        return 'Unclear (' + ' / '.join(names[speaker] for speaker in ambiguous) + reason + ')'
    return names[ordered[0]]


def label_words(words: list[dict], turns: list[SpeakerTurn]) -> str:
    """Keep model IDs consistent per recording and mark uncertain attribution."""
    names: dict[str, str] = {}
    for turn in turns:
        names.setdefault(turn.speaker, f'Person {len(names) + 1}')
    lines: list[str] = []
    current_label = ''
    current_text = ''
    current_start = 0.0
    previous_end = 0.0

    def flush() -> None:
        if current_text:
            minutes, seconds = divmod(current_start, 60)
            lines.append(f'[{int(minutes):02d}:{seconds:05.2f}] {current_label}: {current_text.strip()}')

    for word in words:
        text = str(word.get('text', '')).strip()
        start, end = float(word['start']), float(word['end'])
        if not text:
            continue
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise ValueError('Whisper returned invalid word timestamps.')
        label = _speaker_label(start, end, turns, names) if end > start else 'Unattributed'
        if label != current_label or start - previous_end > 2:
            flush()
            current_text = ''
            current_start = start
            current_label = label
        separator = '' if not current_text or re.match(r'^[,.;:!?\)\]]', text) else ' '
        current_text += separator + text
        previous_end = end
    flush()
    if not lines:
        return 'No speech was transcribed.'
    return ('Speaker labels are automatic and apply only to this recording. '
            'Overlapping voices may be unclear.\n\n' + '\n'.join(lines))


async def _run(*command: str, timeout: int = 1800) -> None:
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    try:
        _stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        if process.returncode:
            # No credentials or full command lines are exposed in errors.
            raise RuntimeError(f'{Path(command[0]).name} could not process the audio. Check the local media/model installation.')
    except asyncio.CancelledError:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    except asyncio.TimeoutError as exc:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise RuntimeError('Speaker labeling timed out. Try a shorter recording.') from exc


async def transcribe_labeled(audio: Path, transcriber: WhisperTranscriber, status: Callable[[str], None] | None = None) -> str:
    """Run NVIDIA first, then Whisper with timestamps, keeping models sequential."""
    binary, model = ensure_available()
    ProjectPaths.ensure_directories()
    await asyncio.to_thread(transcriber.unload_model)
    with TemporaryDirectory(prefix='diarize_', dir=ProjectPaths.RUNTIME_DIR) as temporary:
        directory = Path(temporary)
        wav, rttm = directory / 'audio.wav', directory / 'speakers.rttm'
        if status:
            status('Identifying speakers locally with NVIDIA…')
        await _run('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(audio), '-ac', '1', '-ar', '16000', str(wav))
        await _run(str(binary), 'diarize', str(wav), '--model', str(model), '--preset', 'v3-offline', '--format', 'rttm', '--output', str(rttm), '--force')
        turns = parse_rttm(rttm.read_text())
        if status:
            status('Transcribing words and matching speaker timestamps…')
        words = await transcriber.transcribe_words(wav)
        return label_words(words, turns)
