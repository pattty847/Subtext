"""
Modern audio transcription with Whisper AI.
"""
import asyncio
import gc
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import whisper

try:
    from faster_whisper import WhisperModel
except Exception:  # pragma: no cover
    WhisperModel = None

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

from src.config.paths import ProjectPaths

FFMPEG_DOWNLOAD_URL = "https://www.ffmpeg.org/download.html"


class TranscriptionProgress:
    def __init__(self):
        self.stage = "loading"  # loading, processing, saving
        self.percent = 0.0
        self.message = ""

    def __str__(self):
        return f"{self.stage.title()}: {self.message} ({self.percent:.1f}%)"


class WhisperTranscriber:
    def __init__(
        self,
        model_name: str = "medium.en",
        device: Optional[str] = None,
        backend: str = "auto",
        compute_type: Optional[str] = None,
    ):
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.backend = self._resolve_backend(backend)
        self.compute_type = compute_type or self._resolve_compute_type()
        self.use_fp16 = self.device == "cuda"
        self.model = None

    @staticmethod
    def _resolve_device(device: Optional[str]) -> str:
        """Resolve Whisper runtime device with safe fallbacks."""
        if device and device.strip() and device.lower() != "auto":
            return device.lower()

        if torch is not None:
            try:
                if torch.cuda.is_available():
                    return "cuda"
            except Exception:
                pass

            try:
                mps_backend = getattr(torch.backends, "mps", None)
                if (
                    mps_backend is not None
                    and mps_backend.is_built()
                    and mps_backend.is_available()
                ):
                    return "mps"
            except Exception:
                pass

        return "cpu"

    def _resolve_backend(self, backend: str) -> str:
        """Choose an implementation backend with conservative defaults."""
        requested_backend = (backend or "auto").strip().lower()
        if requested_backend not in {"auto", "openai", "faster-whisper"}:
            requested_backend = "auto"

        if requested_backend == "openai":
            return "openai"

        if requested_backend == "faster-whisper":
            if WhisperModel is None:
                raise RuntimeError(
                    "faster-whisper backend requested but dependency is not installed."
                )
            return "faster-whisper"

        if self.device == "cuda" and WhisperModel is not None:
            return "faster-whisper"

        return "openai"

    def _resolve_compute_type(self) -> str:
        """Pick a safe compute type for the chosen device/backend."""
        if self.backend == "faster-whisper":
            if self.device == "cuda":
                return "float16"
            if self.device == "cpu":
                return "int8"
        return "float32"

    async def load_model(
        self,
        progress_callback: Optional[Callable[[TranscriptionProgress], None]] = None,
    ) -> None:
        """Load Whisper model asynchronously."""
        if self.model is not None:
            return

        progress = TranscriptionProgress()
        progress.stage = "loading"
        progress.message = (
            f"Loading {self.model_name} via {self.backend} on {self.device}..."
        )
        if progress_callback:
            progress_callback(progress)

        loop = asyncio.get_event_loop()

        def _load_model():
            if self.backend == "faster-whisper":
                assert WhisperModel is not None
                return WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
            return whisper.load_model(self.model_name, device=self.device)

        self.model = await loop.run_in_executor(None, _load_model)

        progress.percent = 100.0
        progress.message = "Model loaded successfully"
        if progress_callback:
            progress_callback(progress)

    def unload_model(self):
        """Release loaded Whisper model and clear memory caches."""
        if self.model is not None:
            try:
                del self.model
            except Exception:
                pass
            self.model = None

        gc.collect()
        if torch is not None and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
            except Exception:
                pass

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration in seconds using ffprobe"""
        try:
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'error', '-show_entries',
                    'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                    str(audio_path)
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
            pass
        return 0.0

    def get_audio_duration(self, audio_path: Path) -> float:
        """Public duration helper for callers that need request metadata."""
        return self._get_audio_duration(audio_path)

    @staticmethod
    def _ensure_ffmpeg_available() -> None:
        """Validate ffmpeg/ffprobe binaries are available in PATH."""
        missing_tools = [
            tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None
        ]
        if missing_tools:
            missing = ", ".join(missing_tools)
            raise Exception(
                f"Missing required media tools: {missing}. "
                f"Install FFmpeg: {FFMPEG_DOWNLOAD_URL}"
            )
    
    async def transcribe(
        self,
        audio_path: Path,
        progress_callback: Optional[Callable[[TranscriptionProgress], None]] = None,
    ) -> str:
        """Transcribe audio file to text."""
        self._ensure_ffmpeg_available()

        if self.model is None:
            await self.load_model(progress_callback)

        # Get audio duration for progress estimation
        audio_duration = self._get_audio_duration(audio_path)
        start_time = time.time()
        last_progress_update = 0.0
        transcription_complete = threading.Event()

        progress = TranscriptionProgress()
        progress.stage = "processing"
        progress.message = f"Transcribing {audio_path.name}..."
        progress.percent = 0.0
        if progress_callback:
            progress_callback(progress)

        # Background thread to update progress based on elapsed time
        progress_thread = None
        if progress_callback:
            def update_progress_periodically():
                nonlocal last_progress_update
                update_count = 0
                while not transcription_complete.is_set():
                    elapsed = time.time() - start_time
                    
                    if audio_duration > 0:
                        # Estimate progress: transcription typically takes 2-3x audio duration on GPU
                        # Use a conservative estimate of 2.5x duration
                        estimated_total_time = audio_duration * 2.5
                        estimated_percent = min(95.0, (elapsed / estimated_total_time) * 100)
                    else:
                        # Fallback: show indeterminate progress that slowly increases
                        # Update every 2 seconds, cap at 90% until complete
                        update_count += 1
                        estimated_percent = min(90.0, update_count * 2.0)  # 2% per update, max 90%
                    
                    # Only update if progress increased by at least 0.5%
                    if estimated_percent - last_progress_update >= 0.5:
                        last_progress_update = estimated_percent
                        progress_obj = TranscriptionProgress()
                        progress_obj.stage = "processing"
                        progress_obj.percent = estimated_percent
                        if audio_duration > 0:
                            progress_obj.message = f"Transcribing... {estimated_percent:.1f}%"
                        else:
                            progress_obj.message = f"Transcribing... ({int(elapsed)}s elapsed)"
                        progress_callback(progress_obj)

                    time.sleep(0.5)  # Update every 500ms

            progress_thread = threading.Thread(target=update_progress_periodically, daemon=True)
            progress_thread.start()

        loop = asyncio.get_event_loop()

        def _transcribe():
            if self.backend == "faster-whisper":
                segments, _info = self.model.transcribe(
                    str(audio_path),
                    beam_size=1,
                    vad_filter=True,
                    condition_on_previous_text=False,
                )
                result = " ".join(segment.text.strip() for segment in segments).strip()
            else:
                result = self.model.transcribe(
                    str(audio_path),
                    fp16=self.use_fp16,
                    verbose=True,
                )["text"].strip()
            transcription_complete.set()  # Signal that transcription is done
            return result

        try:
            transcript = await loop.run_in_executor(None, _transcribe)

            # Wait a moment for final progress update
            if progress_thread:
                progress_thread.join(timeout=1.0)

            progress.stage = "saving"
            progress.percent = 100.0
            progress.message = "Transcription complete"
            if progress_callback:
                progress_callback(progress)

            return transcript

        except Exception as e:
            transcription_complete.set()  # Signal error
            if progress_thread:
                progress_thread.join(timeout=0.5)
            raise Exception(f"Transcription failed: {str(e)}")

    async def transcribe_and_save(
        self,
        audio_path: Path,
        output_path: Optional[Path] = None,
        transcripts_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[TranscriptionProgress], None]] = None,
    ) -> tuple[str, Path]:
        """Transcribe and save to file, returns (transcript_text, output_file_path)."""

        transcript = await self.transcribe(audio_path, progress_callback)

        if output_path is None:
            # Save to organized transcripts directory
            if transcripts_dir:
                output_path = transcripts_dir / f"{audio_path.stem}.txt"
            else:
                # Use default transcripts directory
                ProjectPaths.ensure_directories()
                output_path = ProjectPaths.TRANSCRIPTS_DIR / f"{audio_path.stem}.txt"
            
        progress = TranscriptionProgress()
        progress.stage = "saving"
        progress.message = f"Saving to {output_path.name}..."
        progress.percent = 90.0
        if progress_callback:
            progress_callback(progress)

        output_path.write_text(transcript, encoding='utf-8')

        progress.percent = 100.0
        progress.message = f"Saved to {output_path.name}"
        if progress_callback:
            progress_callback(progress)

        return transcript, output_path


async def test_transcriber():
    """Test the transcriber with a sample file"""
    transcriber = WhisperTranscriber()
    
    def progress_callback(progress: TranscriptionProgress):
        print(f"\r{progress}", end="", flush=True)
    
    # For testing, you'd need an actual audio file
    # audio_path = Path("test_audio.mp4")
    # if audio_path.exists():
    #     transcript, output_file = await transcriber.transcribe_and_save(audio_path, progress_callback=progress_callback)
    #     print(f"\nTranscript saved to: {output_file}")
    #     print(f"First 200 chars: {transcript[:200]}...")
    # else:
    #     print("No test audio file found")
    
    print("Transcriber ready for use")


if __name__ == "__main__":
    asyncio.run(test_transcriber())
