"""
Command-line access to the always-on Subtext private web service.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from email.message import Message
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from src.config.paths import ProjectPaths


DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
CHUNK_SIZE = 1024 * 1024


def _safe_filename(value: str, default: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    return cleaned or default


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _source_stem(source_name: str) -> str:
    parsed = urlparse(source_name)
    if parsed.scheme and parsed.netloc:
        raw = parsed.netloc + parsed.path
        if parsed.query:
            raw = f"{raw}_{parsed.query}"
    else:
        raw = Path(source_name).stem
    return _safe_filename(raw, "transcript")


def _filename_from_content_disposition(header: str) -> Optional[str]:
    if not header:
        return None

    message = Message()
    message["content-disposition"] = header
    filename = message.get_filename()
    if not filename:
        return None
    return _safe_filename(Path(filename).name, "download")


def _fallback_download_name(url: str) -> str:
    parsed = urlparse(url)
    source = Path(parsed.path).name if parsed.path else ""
    return _safe_filename(source, "download")


def save_transcript_result(
    result: dict[str, Any],
    *,
    output_dir: Path = ProjectPaths.DOWNLOADS_DIR,
    source_name: str = "transcript",
) -> Path:
    """Save a transcription API result as a text file and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_text = str(result.get("text", "")).strip()
    output_path = _unique_path(output_dir / f"{_source_stem(source_name)}.txt")
    output_path.write_text(f"{transcript_text}\n", encoding="utf-8")
    return output_path


def read_source_list(path: Path) -> list[str]:
    """Read newline-delimited URLs/files, ignoring blank lines and comments."""
    sources: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            sources.append(stripped)
    return sources


class SubtextApiClient:
    """Small client for Subtext's private FastAPI service."""

    def __init__(
        self,
        server_url: str = DEFAULT_SERVER_URL,
        *,
        api_key: str = "",
        session: Optional[requests.Session] = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key.strip()
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"x-subtext-key": self.api_key}

    def transcribe_url(self, url: str) -> dict[str, Any]:
        response = self.session.post(
            f"{self.server_url}/transcribe",
            data={"url": url},
            headers=self._headers(),
            timeout=None,
        )
        response.raise_for_status()
        return dict(response.json())

    def transcribe_file(self, file_path: Path) -> dict[str, Any]:
        with file_path.open("rb") as handle:
            response = self.session.post(
                f"{self.server_url}/transcribe",
                files={"file": (file_path.name, handle)},
                headers=self._headers(),
                timeout=None,
            )
        response.raise_for_status()
        return dict(response.json())

    def _download_attachment(
        self,
        endpoint: str,
        url: str,
        *,
        output_dir: Path = ProjectPaths.DOWNLOADS_DIR,
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        response = self.session.post(
            f"{self.server_url}/{endpoint}",
            data={"url": url},
            headers=self._headers(),
            stream=True,
            timeout=None,
        )
        response.raise_for_status()

        filename = _filename_from_content_disposition(
            response.headers.get("content-disposition", "")
        )
        if not filename:
            filename = _fallback_download_name(url)

        output_path = _unique_path(output_dir / filename)
        with output_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    handle.write(chunk)
        return output_path

    def download_video(
        self,
        url: str,
        *,
        output_dir: Path = ProjectPaths.DOWNLOADS_DIR,
    ) -> Path:
        return self._download_attachment("download-video", url, output_dir=output_dir)

    def download_audio(
        self,
        url: str,
        *,
        output_dir: Path = ProjectPaths.DOWNLOADS_DIR,
    ) -> Path:
        return self._download_attachment("download-audio", url, output_dir=output_dir)


def download_url_list(
    client: SubtextApiClient,
    urls: list[str],
    *,
    output_dir: Path = ProjectPaths.DOWNLOADS_DIR,
    audio_only: bool = False,
) -> list[Path]:
    """Download each URL sequentially through the running service."""
    saved_paths: list[Path] = []
    downloader = client.download_audio if audio_only else client.download_video
    for url in urls:
        saved_paths.append(downloader(url, output_dir=output_dir))
    return saved_paths


def _default_server_url() -> str:
    return os.getenv("SUBTEXT_SERVER_URL", DEFAULT_SERVER_URL).strip() or DEFAULT_SERVER_URL


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subtext",
        description="Programmatic command-line access to a running Subtext private service.",
    )
    parser.add_argument(
        "--server-url",
        default=_default_server_url(),
        help=f"Subtext service URL. Defaults to {DEFAULT_SERVER_URL}.",
    )
    parser.add_argument(
        "--key",
        default=os.getenv("SUBTEXT_SERVER_KEY", ""),
        help="Shared service key. Defaults to SUBTEXT_SERVER_KEY.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ProjectPaths.DOWNLOADS_DIR,
        help="Where downloaded media and transcripts are saved.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    transcribe = subparsers.add_parser(
        "transcribe",
        help="Transcribe a URL or local audio/video file through the running service.",
    )
    transcribe.add_argument("source", help="Media URL or local audio/video path.")
    transcribe.add_argument(
        "--json",
        action="store_true",
        help="Print the full API response as JSON after saving the transcript.",
    )

    download = subparsers.add_parser(
        "download",
        help="Download a URL video through the running service.",
    )
    download.add_argument("url", help="Media URL to download.")

    download_audio = subparsers.add_parser(
        "download-audio",
        help="Download the highest-quality audio-only stream through the running service.",
    )
    download_audio.add_argument("url", help="Media URL to download as audio.")

    download_list = subparsers.add_parser(
        "download-list",
        help="Download each URL from a newline-delimited file.",
    )
    download_list.add_argument("source_file", type=Path, help="Text file of reviewed URLs.")
    download_list.add_argument(
        "--audio-only",
        action="store_true",
        help="Download the best available audio-only stream for each URL.",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    client = SubtextApiClient(args.server_url, api_key=args.key)

    try:
        if args.command == "download":
            saved_path = client.download_video(args.url, output_dir=output_dir)
            print(saved_path)
            return 0

        if args.command == "download-audio":
            saved_path = client.download_audio(args.url, output_dir=output_dir)
            print(saved_path)
            return 0

        if args.command == "download-list":
            urls = read_source_list(args.source_file.expanduser())
            for saved_path in download_url_list(
                client,
                urls,
                output_dir=output_dir,
                audio_only=args.audio_only,
            ):
                print(saved_path)
            return 0

        source = args.source
        source_path = Path(source).expanduser()
        if source_path.exists():
            result = client.transcribe_file(source_path)
        else:
            result = client.transcribe_url(source)

        saved_path = save_transcript_result(
            result,
            output_dir=output_dir,
            source_name=source,
        )
        print(saved_path)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except requests.RequestException as error:
        print(f"Subtext request failed: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Subtext file operation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
