"""
Modern YouTube downloader with progress tracking
"""
import asyncio
import html
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional
import yt_dlp
from yt_dlp.utils import DownloadError

from src.config.paths import ProjectPaths


class DownloadProgress:
    def __init__(self):
        self.percent = 0.0
        self.speed = ""
        self.eta = ""
        self.filename = ""

    def __str__(self):
        return f"{self.percent:.1f}% - {self.speed} - ETA: {self.eta}"


class UniversalDownloader:
    YT_COOKIE_BROWSER_ORDER = ("edge", "chrome", "brave", "firefox")

    def __init__(self, output_dir: Optional[Path] = None):
        if output_dir is None:
            # Use new assets structure
            self.downloads_dir = ProjectPaths.VIDEOS_DIR
            self.transcripts_dir = ProjectPaths.TRANSCRIPTS_DIR
        else:
            self.downloads_dir = output_dir / "videos"
            self.transcripts_dir = output_dir / "transcripts"
        
        # Ensure directories exist
        ProjectPaths.ensure_directories()
        
        # Keep backwards compatibility
        self.output_dir = self.downloads_dir
        
    def _progress_hook(self, d, callback: Optional[Callable[[DownloadProgress], None]] = None):
        """Progress callback for yt-dlp"""
        if callback and d['status'] == 'downloading':
            progress = DownloadProgress()
            
            # Clean and parse percentage
            percent_str = d.get('_percent_str', '0')
            if percent_str:
                # Remove ANSI codes and non-numeric characters except decimal point
                import re
                clean_percent = re.sub(r'\x1b\[[0-9;]*m', '', str(percent_str))  # Remove ANSI codes
                clean_percent = re.sub(r'[^\d.]', '', clean_percent)  # Keep only digits and decimal
                try:
                    progress.percent = float(clean_percent) if clean_percent else 0.0
                except ValueError:
                    progress.percent = 0.0
            else:
                progress.percent = 0.0
                
            progress.speed = d.get('_speed_str', '')
            progress.eta = d.get('_eta_str', '')
            progress.filename = Path(d.get('filename', '')).name
            callback(progress)

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        """Return True if URL appears to be a YouTube link."""
        lowered = (url or "").lower()
        return "youtube.com" in lowered or "youtu.be" in lowered

    @staticmethod
    def _clean_caption_line(line: str) -> str:
        """Normalize caption line content."""
        text = re.sub(r"<[^>]+>", "", line)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _normalize_timestamp(raw: str) -> str:
        """Convert VTT/SRT time to HH:MM:SS."""
        ts = raw.strip().replace(",", ".")
        parts = ts.split(":")
        if len(parts) == 3:
            hh, mm, ss = parts
            sec = ss.split(".")[0]
            return f"{int(hh):02d}:{int(mm):02d}:{int(sec):02d}"
        if len(parts) == 2:
            mm, ss = parts
            sec = ss.split(".")[0]
            return f"00:{int(mm):02d}:{int(sec):02d}"
        return "00:00:00"

    def parse_caption_text(self, caption_path: Path, include_timestamps: bool = True) -> str:
        """Parse VTT/SRT captions into clean transcript text."""
        raw = caption_path.read_text(encoding="utf-8", errors="ignore")
        lines = raw.splitlines()
        parsed_lines = []
        current_timestamp = ""
        cue_lines = []
        last_text = ""

        def flush_cue():
            nonlocal cue_lines, last_text
            if not cue_lines:
                return
            joined = self._clean_caption_line(" ".join(cue_lines))
            cue_lines = []
            if not joined or joined == last_text:
                return
            last_text = joined
            if include_timestamps and current_timestamp:
                parsed_lines.append(f"[{current_timestamp}] {joined}")
            else:
                parsed_lines.append(joined)

        for line in lines:
            stripped = line.strip()
            if not stripped:
                flush_cue()
                continue
            if stripped.upper().startswith("WEBVTT") or stripped.startswith("Kind:") or stripped.startswith("Language:"):
                continue
            if stripped.startswith("NOTE"):
                continue
            if stripped.isdigit():
                continue
            if "-->" in stripped:
                flush_cue()
                start = stripped.split("-->", 1)[0].strip()
                current_timestamp = self._normalize_timestamp(start)
                continue
            cue_lines.append(stripped)

        flush_cue()
        return "\n".join(parsed_lines).strip()

    async def download_youtube_captions(
        self,
        url: str,
        include_timestamps: bool = True,
        use_browser_cookies: bool = True,
        max_retries: int = 3,
        backoff_base_seconds: float = 8.0,
    ) -> tuple[str, Path]:
        """Download YouTube captions and return (parsed_text, saved_txt_path)."""
        if not self.is_youtube_url(url):
            raise Exception("Not a YouTube URL")

        loop = asyncio.get_event_loop()
        browser_sources = [None]
        if use_browser_cookies:
            configured = os.getenv("TRANSCRIPTAI_YT_BROWSER", "").strip().lower()
            browser_sources = []
            if configured:
                browser_sources.append(configured)
            browser_sources.extend(self.YT_COOKIE_BROWSER_ORDER)
            # remove duplicates while preserving order
            browser_sources = list(dict.fromkeys(browser_sources))
            # fallback anonymous attempt at the end
            browser_sources.append(None)

        def _download_subtitles(cookie_browser: Optional[str]) -> tuple[str, Path]:
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitlesformat": "vtt/srt/best",
                # Only English variants — ".*" would download every language and then
                # we'd pick one at random.  Non-English audio falls through to Whisper.
                "subtitleslangs": ["en", "en-orig", "en-US", "en-GB", "en-.*"],
                "outtmpl": str(self.transcripts_dir / "%(title).80B [%(id)s].%(ext)s"),
                "quiet": True,
                "noprogress": True,
                "no_warnings": True,
                "windowsfilenames": True,
                "restrictfilenames": True,
                "no_color": True,
            }
            if cookie_browser:
                ydl_opts["cookiesfrombrowser"] = (cookie_browser,)
            # Support a Netscape-format cookies file for server deployments where
            # browser-based cookie extraction is unavailable.
            # Set SUBTEXT_YT_COOKIES=/path/to/cookies.txt (exported from your browser).
            cookies_file = os.getenv("SUBTEXT_YT_COOKIES", "").strip()
            if cookies_file and Path(cookies_file).exists():
                ydl_opts["cookiefile"] = cookies_file

            before_files = {p.resolve() for p in self.transcripts_dir.glob("*")}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = str(info.get("id", "")).strip()

            candidates = []
            for path in self.transcripts_dir.glob("*"):
                if path.resolve() in before_files:
                    continue
                if path.suffix.lower() not in {".vtt", ".srt"}:
                    continue
                name = path.name
                # video_id appears literally in the filename regardless of whether
                # restrictfilenames replaced surrounding brackets with underscores
                if video_id and video_id not in name:
                    continue
                candidates.append(path)

            if not candidates:
                # Fallback: pick the newest subtitle-like file added in this run.
                for path in self.transcripts_dir.glob("*"):
                    if path.resolve() in before_files:
                        continue
                    if path.suffix.lower() in {".vtt", ".srt"}:
                        candidates.append(path)

            if not candidates:
                raise Exception("No YouTube caption track found (manual or auto-generated).")

            caption_path = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
            transcript_text = self.parse_caption_text(caption_path, include_timestamps=include_timestamps)
            if not transcript_text:
                raise Exception("Caption file downloaded but produced empty transcript text.")

            output_name = caption_path.stem + ".txt"
            output_path = self.transcripts_dir / output_name
            output_path.write_text(transcript_text, encoding="utf-8")
            return transcript_text, output_path

        last_error = None
        for browser in browser_sources:
            for attempt in range(max_retries + 1):
                try:
                    return await loop.run_in_executor(None, _download_subtitles, browser)
                except DownloadError as e:
                    last_error = e
                    msg = str(e)
                    if "429" in msg or "Too Many Requests" in msg:
                        if attempt < max_retries:
                            delay = backoff_base_seconds * (2 ** attempt)
                            await asyncio.sleep(delay)
                            continue
                        # try next browser source after retries exhausted
                        break
                    # Non-rate-limit errors: move to next browser source
                    break
                except Exception as e:
                    last_error = e
                    # Captions missing/parse issues: move to next source quickly
                    break

        msg = str(last_error) if last_error else "unknown subtitle download error"
        if "429" in msg or "Too Many Requests" in msg:
            raise Exception(
                "YouTube subtitle request was rate-limited (HTTP 429) after retries. "
                "Whisper fallback will be used."
            )
        raise Exception(f"YouTube captions unavailable: {msg}")

    async def download(self, url: str, progress_callback: Optional[Callable[[DownloadProgress], None]] = None) -> Path:
        """Download video and return path to downloaded file"""
        
        # Configure yt-dlp options
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': str(self.output_dir / '%(title).80B [%(id)s].%(ext)s'),
            'restrictfilenames': True,
            'windowsfilenames': True,
            'progress_hooks': [lambda d: self._progress_hook(d, progress_callback)],
            'quiet': True,
            'no_warnings': True,
            'no_color': True,  # Disable ANSI color codes
        }
        
        # Run download in thread to avoid blocking UI
        loop = asyncio.get_event_loop()
        
        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Get the actual filename
                filename = ydl.prepare_filename(info)
                return Path(filename)
        
        try:
            filepath = await loop.run_in_executor(None, _download)
            return filepath
        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")


async def test_downloader():
    """Test the downloader"""
    downloader = UniversalDownloader()
    
    def progress_callback(progress: DownloadProgress):
        print(f"\r{progress}", end="", flush=True)
    
    try:
        # Test with a short video (works with any supported site)
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll - short and safe for testing
        filepath = await downloader.download(url, progress_callback)
        print(f"\nDownloaded: {filepath}")
        return filepath
    except Exception as e:
        print(f"\nError: {e}")
        return None


if __name__ == "__main__":
    asyncio.run(test_downloader())
