"""Connect profile browsing to a browser's existing Instagram login."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import instaloader
from yt_dlp.cookies import extract_cookies_from_browser
from src.core.instagram_profiles import connection_paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', choices=['chrome', 'firefox', 'safari'], required=True)
    args = parser.parse_args()
    jar = extract_cookies_from_browser(args.browser)
    loader = instaloader.Instaloader(quiet=True, max_connection_attempts=1, request_timeout=15)
    for cookie in jar:
        if cookie.domain.lstrip('.') == 'instagram.com' or cookie.domain.endswith('.instagram.com'):
            loader.context._session.cookies.set_cookie(cookie)
    # Import locally without hitting a login-check endpoint, which Instagram
    # can rate-limit separately from normal browser access.
    if not loader.context._session.cookies.get_dict().get('sessionid'):
        raise SystemExit('No Instagram session found. Sign into Instagram in that browser, then retry.')
    username = 'browser-session'
    loader.context.username = username
    session, account = connection_paths()
    session.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Set restrictive permissions before writing cookies.
    descriptor = os.open(session, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    os.close(descriptor)
    session.chmod(0o600)
    loader.save_session_to_file(str(session))
    account.write_text(json.dumps({'username': username})+'\n')
    account.chmod(0o600)
    print('Chrome Instagram session saved locally. Live profile access still depends on Instagram accepting requests.')


if __name__ == '__main__':
    main()
