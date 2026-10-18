"""Bounded, paginated Instagram profile lookup with local session support."""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import instaloader
import requests

from src.config.paths import ProjectPaths
from src.core import instagram_grid

PAGE_SIZE = 12
SESSION_TTL = 15 * 60
MAX_BROWSERS = 16
_USERNAME = re.compile(r'^[A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?$')
_RESERVED = {'p', 'reel', 'reels', 'stories', 'explore', 'accounts', 'direct', 'share', 'tv'}


class ProfileLookupError(ValueError):
    """A profile cannot be loaded; message is safe to show to the user."""


def profile_username(value: str) -> str:
    """Normalize a handle or Instagram profile URL without following links."""
    value = value.strip()
    if value.startswith(('instagram.com/', 'www.instagram.com/')):
        value = 'https://' + value
    if '://' in value or '/' in value:
        parsed = urlparse(value)
        if parsed.scheme != 'https' or parsed.hostname not in {'instagram.com', 'www.instagram.com'} or parsed.port not in {None, 443}:
            raise ValueError('Use an Instagram profile URL or @handle.')
        parts = parsed.path.strip('/').split('/')
        if len(parts) != 1:
            raise ValueError('Use a creator profile, not an individual post or reel.')
        value = parts[0]
    value = value.removeprefix('@')
    if not _USERNAME.fullmatch(value) or value.lower() in _RESERVED:
        raise ValueError('Enter a valid Instagram username or profile URL.')
    return value.lower()


def connection_paths() -> tuple[Path, Path]:
    """Session files live in the ignored project runtime directory."""
    directory = ProjectPaths.RUNTIME_DIR / 'instagram'
    return directory / 'session', directory / 'account.json'


def _loader() -> instaloader.Instaloader:
    loader = instaloader.Instaloader(quiet=True, max_connection_attempts=1, request_timeout=15)
    session, account = connection_paths()
    username = os.getenv('SUBTEXT_INSTAGRAM_USERNAME', '').strip()
    if account.is_file():
        username = json.loads(account.read_text())['username']
    if session.is_file() and username:
        loader.load_session_from_file(username, str(session))
    return loader


def _cache_thumbnail(shortcode: str, url: str) -> bool:
    """Cache provider thumbnails without forwarding Instagram credentials."""
    host = (urlparse(url).hostname or '').lower()
    if urlparse(url).scheme != 'https' or not any(host.endswith('.' + suffix) for suffix in ['cdninstagram.com', 'fbcdn.net']):
        return False
    path = instagram_grid.thumbnail_cache_path(shortcode)
    if path.exists():
        return True
    temp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    try:
        with requests.get(url, timeout=15, stream=True, allow_redirects=False) as response:
            if response.status_code != 200 or not response.headers.get('Content-Type', '').startswith('image/'):
                return False
            size = 0
            with temp.open('wb') as stream:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > instagram_grid.MAX_THUMB_BYTES:
                        return False
                    stream.write(chunk)
            if not size:
                return False
            temp.replace(path)
            return True
    except (requests.RequestException, OSError):
        return False
    finally:
        temp.unlink(missing_ok=True)


class ProfileBrowser:
    """Keep opaque cursors local, bounded and serialized across requests."""

    def __init__(self) -> None:
        self._pages: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._retry_after = 0.0

    async def page(self, creator: str, cursor: str = '') -> dict[str, Any]:
        username = profile_username(creator)
        async with self._lock:
            return await asyncio.to_thread(self._page, username, cursor)

    def _page(self, username: str, cursor: str) -> dict[str, Any]:
        now = time.monotonic()
        if now < self._retry_after:
            raise ProfileLookupError('Instagram temporarily limited profile access. Wait a few minutes before loading a profile again. Individual reel links still work.')
        self._pages = {key: value for key, value in self._pages.items() if now - value['updated'] < SESSION_TTL}
        try:
            if cursor:
                state = self._pages.pop(cursor, None)
                if not state or state['username'] != username:
                    raise ValueError('This profile page expired. Load the creator again.')
            else:
                loader = _loader()
                profile = instaloader.Profile.from_username(loader.context, username)
                if profile.is_private and not profile.followed_by_viewer:
                    raise ProfileLookupError('This profile is private. Connect an Instagram account that follows it on the Mac.')
                state = {'username': username, 'name': profile.full_name, 'iterator': iter(profile.get_posts()), 'updated': now}
            posts = []
            exhausted = False
            for _ in range(PAGE_SIZE):
                try:
                    post = next(state['iterator'])
                except StopIteration:
                    exhausted = True
                    break
                shortcode = post.shortcode
                if not instagram_grid.SHORTCODE_RE.fullmatch(shortcode):
                    continue
                video = post.is_video or (post.typename == 'GraphSidecar' and any(post.get_is_videos()))
                cached = _cache_thumbnail(shortcode, post.url)
                posts.append({'shortcode': shortcode, 'url': instagram_grid.canonical_post_url(shortcode), 'title': post.caption or 'Instagram post', 'caption': post.caption or '', 'ok': True, 'selectable': video, 'media_type': 'video' if video else 'photo', 'thumb': f'/ig/thumb/{shortcode}' if cached else None, 'error': ''})
            next_cursor = ''
            if not exhausted:
                if len(self._pages) >= MAX_BROWSERS:
                    oldest = min(self._pages, key=lambda key: self._pages[key]['updated'])
                    del self._pages[oldest]
                next_cursor = uuid.uuid4().hex
                state['updated'] = time.monotonic()
                self._pages[next_cursor] = state
            return {'creator': {'username': username, 'name': state['name'], 'url': f'https://www.instagram.com/{username}/'}, 'posts': posts, 'cursor': next_cursor}
        except instaloader.exceptions.ProfileNotExistsException as exc:
            raise ProfileLookupError('Instagram could not find that creator.') from exc
        except instaloader.exceptions.InstaloaderException as exc:
            self._retry_after = time.monotonic() + 180
            raise ProfileLookupError('Instagram blocked or rate-limited profile lookup. Wait a few minutes; if it persists, reconnect Instagram on the Mac. Individual reel links still work.') from exc
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise ProfileLookupError('The local Instagram connection could not be read. Reconnect Instagram on the Mac.') from exc
