"""
Instagram grid helpers for the private web service.

Resolves a list of Instagram post/reel URLs into grid cards with thumbnails.

Two facts shape this module:

1. Instagram's profile pages are login-walled and yt-dlp's ``instagram:user``
   extractor is currently marked broken, so a handle -> post-list lookup cannot
   run on the box. Post *lists* come from elsewhere (the user pastes links, or
   an agent with Instagram access supplies them).
2. Individual post pages are public. Each one carries ``og:image`` /
   ``og:title`` / ``og:description`` meta tags with no login required, so
   thumbnails are fetched per post over plain HTTPS.

Downloaded thumbnail bytes are cached on disk keyed by shortcode, so repeat
grid views are free and the phone never hotlinks expiring CDN URLs directly.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from src.config.paths import ProjectPaths

LOGGER = logging.getLogger("subtext.instagram_grid")

# iPhone Safari UA: Instagram serves the full public post page to it,
# including og:* meta tags. (The /embed/ variant omits the post image.)
IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,64}$")
_POST_PATH_RE = re.compile(r"^/(?:p|reel|reels)/([A-Za-z0-9_-]+)/?", re.IGNORECASE)
_OG_TAG_RE = re.compile(
    r'<meta\s+property="og:(image|title|description)"\s+content="([^"]*)"',
    re.IGNORECASE,
)

REQUEST_TIMEOUT_SECONDS = 15
MAX_THUMB_BYTES = 5 * 1024 * 1024
# How many post pages to fetch concurrently. Small on purpose: polite to
# Instagram and kind to the box.
FETCH_CONCURRENCY = 4
# Sanity cap per grid request.
MAX_GRID_POSTS = 24


def extract_shortcode(raw_url: str) -> Optional[str]:
    """Return the post shortcode for an Instagram post/reel URL, else None."""
    try:
        path = urlparse((raw_url or "").strip()).path or ""
    except ValueError:
        return None
    match = _POST_PATH_RE.match(path)
    if not match:
        return None
    shortcode = match.group(1)
    return shortcode if SHORTCODE_RE.match(shortcode) else None


def is_instagram_post_url(raw_url: str) -> bool:
    """True when the URL is an instagram.com post/reel link with a shortcode."""
    try:
        host = (urlparse((raw_url or "").strip()).hostname or "").lower()
    except ValueError:
        return False
    if host not in {"instagram.com", "www.instagram.com"}:
        return False
    return extract_shortcode(raw_url) is not None


def canonical_post_url(shortcode: str) -> str:
    """Canonical public URL for a shortcode."""
    return f"https://www.instagram.com/p/{shortcode}/"


def thumbnail_cache_dir() -> Path:
    """Disk cache for thumbnail bytes, keyed by shortcode."""
    cache_dir = ProjectPaths.RUNTIME_DIR / "ig_thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def thumbnail_cache_path(shortcode: str) -> Path:
    return thumbnail_cache_dir() / f"{shortcode}.jpg"


def _parse_og_tags(page_html: str) -> dict[str, str]:
    """Extract og:image / og:title / og:description from post page HTML."""
    tags: dict[str, str] = {}
    for name, content in _OG_TAG_RE.findall(page_html or ""):
        key = name.lower()
        if key not in tags:
            tags[key] = html.unescape(content).strip()
    return tags


def _fetch_post_card(shortcode: str) -> dict[str, Any]:
    """Fetch one post page + its thumbnail. Runs in a worker thread.

    Returns a card dict. Never raises: failures produce a card with
    ``ok=False`` and an ``error`` message so one bad post can't sink the grid.
    """
    card: dict[str, Any] = {
        "shortcode": shortcode,
        "url": canonical_post_url(shortcode),
        "ok": False,
        "title": "",
        "caption": "",
        "error": "",
    }
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": IPHONE_UA})
        page = session.get(
            canonical_post_url(shortcode),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        page.raise_for_status()
        tags = _parse_og_tags(page.text)
        image_url = tags.get("image", "")
        if not image_url:
            card["error"] = "No thumbnail found on the post page."
            return card

        card["title"] = tags.get("title", "")
        # og:description is usually `"caption" on Instagram` or the caption
        # text itself; strip the trailing attribution when present.
        description = tags.get("description", "")
        caption = re.sub(r"\s+on Instagram\s*$", "", description).strip().strip('"')
        card["caption"] = caption

        thumb_path = thumbnail_cache_path(shortcode)
        if not thumb_path.exists():
            image_resp = session.get(image_url, timeout=REQUEST_TIMEOUT_SECONDS, stream=True)
            image_resp.raise_for_status()
            content_type = (image_resp.headers.get("Content-Type") or "").lower()
            if "image" not in content_type:
                card["error"] = f"Thumbnail URL did not return an image ({content_type})."
                return card
            total = 0
            with thumb_path.open("wb") as handle:
                for chunk in image_resp.iter_content(chunk_size=64 * 1024):
                    total += len(chunk)
                    if total > MAX_THUMB_BYTES:
                        break
                    handle.write(chunk)
            if total > MAX_THUMB_BYTES:
                thumb_path.unlink(missing_ok=True)
                card["error"] = "Thumbnail too large; skipped."
                return card
            if total == 0:
                thumb_path.unlink(missing_ok=True)
                card["error"] = "Thumbnail download returned no data."
                return card

        card["ok"] = True
        return card
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        card["error"] = f"Instagram returned HTTP {status} for this post."
        LOGGER.warning("ig_grid_post_failed shortcode=%s err=%s", shortcode, exc)
        return card
    except requests.RequestException as exc:
        card["error"] = "Could not reach Instagram for this post."
        LOGGER.warning("ig_grid_post_failed shortcode=%s err=%s", shortcode, exc)
        return card
    except OSError as exc:
        card["error"] = "Could not cache the thumbnail."
        LOGGER.warning("ig_grid_thumb_cache_failed shortcode=%s err=%s", shortcode, exc)
        return card


async def resolve_grid(raw_urls: list[str]) -> list[dict[str, Any]]:
    """Resolve IG post URLs into grid cards with cached thumbnails.

    Dedupes by shortcode, caps at MAX_GRID_POSTS, fetches concurrently with
    a small semaphore. Order follows the input list.
    """
    seen: dict[str, str] = {}
    for raw in raw_urls or []:
        shortcode = extract_shortcode(raw)
        if shortcode and shortcode not in seen:
            seen[shortcode] = raw
        if len(seen) >= MAX_GRID_POSTS:
            break

    shortcodes = list(seen.keys())
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def _one(shortcode: str) -> dict[str, Any]:
        async with semaphore:
            return await asyncio.to_thread(_fetch_post_card, shortcode)

    cards = await asyncio.gather(*(_one(code) for code in shortcodes))
    ok_count = sum(1 for card in cards if card.get("ok"))
    LOGGER.info("ig_grid_resolved requested=%s ok=%s", len(shortcodes), ok_count)
    return list(cards)
