"""
Resolve plain track-title crates to reviewable YouTube search candidates.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

import yt_dlp


@dataclass(frozen=True)
class SearchResult:
    query: str
    found: bool
    title: str
    uploader: str
    url: str
    duration: Optional[int]
    error: str


def read_track_titles(path: Path) -> list[str]:
    """Read a newline-delimited crate file, ignoring blanks and comments."""
    titles: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            titles.append(stripped)
    return titles


def resolve_youtube_candidate(query: str) -> SearchResult:
    """Resolve one track title to the top YouTube search candidate."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "default_search": "ytsearch1",
        "noplaylist": True,
        "no_color": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
    except Exception as error:  # noqa: BLE001
        return SearchResult(
            query=query,
            found=False,
            title="",
            uploader="",
            url="",
            duration=None,
            error=str(error),
        )

    entries = info.get("entries") or []
    if not entries:
        return SearchResult(
            query=query,
            found=False,
            title="",
            uploader="",
            url="",
            duration=None,
            error="No result found",
        )

    first = entries[0]
    video_id = str(first.get("id") or "").strip()
    webpage_url = str(first.get("webpage_url") or first.get("url") or "").strip()
    if video_id and not webpage_url.startswith("http"):
        webpage_url = f"https://www.youtube.com/watch?v={video_id}"

    return SearchResult(
        query=query,
        found=True,
        title=str(first.get("title") or "").strip(),
        uploader=str(first.get("uploader") or first.get("channel") or "").strip(),
        url=webpage_url,
        duration=first.get("duration"),
        error="",
    )


def resolve_track_titles(titles: Iterable[str]) -> list[SearchResult]:
    """Resolve many track titles sequentially."""
    return [resolve_youtube_candidate(title) for title in titles]


def _clean_tsv_value(value: object) -> str:
    return str(value if value is not None else "").replace("\t", " ").replace("\n", " ")


def write_resolution_files(
    results: Iterable[SearchResult],
    output_prefix: Path,
) -> dict[str, Path]:
    """Write TSV, JSONL, and URL-only outputs for review and later processing."""
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    result_list = list(results)

    tsv_path = output_prefix.with_suffix(".youtube.tsv")
    jsonl_path = output_prefix.with_suffix(".youtube.jsonl")
    urls_path = output_prefix.with_suffix(".youtube.urls.txt")

    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["query", "found", "title", "uploader", "duration", "url", "error"])
        for result in result_list:
            writer.writerow(
                [
                    _clean_tsv_value(result.query),
                    "true" if result.found else "false",
                    _clean_tsv_value(result.title),
                    _clean_tsv_value(result.uploader),
                    _clean_tsv_value(result.duration),
                    _clean_tsv_value(result.url),
                    _clean_tsv_value(result.error),
                ]
            )

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for result in result_list:
            handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")

    with urls_path.open("w", encoding="utf-8") as handle:
        for result in result_list:
            if result.found and result.url:
                handle.write(result.url + "\n")

    return {"tsv": tsv_path, "jsonl": jsonl_path, "urls": urls_path}
