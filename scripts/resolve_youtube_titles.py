#!/usr/bin/env python3
"""
Resolve a newline-delimited crate of track titles to YouTube search candidates.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.youtube_resolver import read_track_titles, resolve_track_titles, write_resolution_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search YouTube for each track title and write reviewable candidate files.",
    )
    parser.add_argument("crate_file", type=Path, help="Newline-delimited track title file.")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=None,
        help="Output prefix. Defaults to the crate file path without extension.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    crate_file = args.crate_file.expanduser().resolve()
    output_prefix = args.output_prefix
    if output_prefix is None:
        output_prefix = crate_file.with_suffix("")
    else:
        output_prefix = output_prefix.expanduser().resolve()

    titles = read_track_titles(crate_file)
    if not titles:
        print(f"No track titles found in {crate_file}", file=sys.stderr)
        return 1

    print(f"Resolving {len(titles)} tracks...")
    results = resolve_track_titles(titles)
    output_paths = write_resolution_files(results, output_prefix)

    found_count = sum(1 for result in results if result.found)
    print(f"Found candidates for {found_count}/{len(results)} tracks.")
    print(f"Review: {output_paths['tsv']}")
    print(f"JSONL:  {output_paths['jsonl']}")
    print(f"URLs:   {output_paths['urls']}")
    return 0 if found_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
