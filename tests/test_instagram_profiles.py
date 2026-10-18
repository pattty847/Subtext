import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.core import instagram_profiles as profiles


class FakePost:
    def __init__(self, number: int, video: bool = True) -> None:
        self.shortcode = f'AbCd{number:03d}'
        self.caption = f'Post {number}'
        self.is_video = video
        self.typename = 'GraphVideo' if video else 'GraphImage'
        self.url = 'https://scontent.example.cdninstagram.com/image.jpg'


class InstagramProfileTests(unittest.TestCase):
    def test_handle_and_profile_validation_rejects_other_hosts_and_post_paths(self) -> None:
        for value in ['@Creator', 'https://www.instagram.com/Creator/?igsh=abc', 'instagram.com/Creator/']:
            self.assertEqual(profiles.profile_username(value), 'creator')
        for value in ['https://evil.example/creator/', 'https://instagram.com.evil.example/user', 'https://instagram.com/reel/AbcDef/', '../secret', '@', 'https://instagram.com:444/user/']:
            with self.assertRaises(ValueError, msg=value):
                profiles.profile_username(value)

    def test_pages_preserve_order_and_photo_context_and_expire_cursors(self) -> None:
        fake = SimpleNamespace(full_name='Creator Name', is_private=False, get_posts=lambda: iter([FakePost(i, i != 2) for i in range(14)]))
        with patch.object(profiles, '_loader', return_value=SimpleNamespace(context=None)), patch.object(profiles.instaloader.Profile, 'from_username', return_value=fake), patch.object(profiles, '_cache_thumbnail', return_value=True):
            async def run() -> None:
                browser = profiles.ProfileBrowser()
                first = await browser.page('@creator')
                self.assertEqual(len(first['posts']), 12)
                self.assertFalse(first['posts'][2]['selectable'])
                self.assertEqual(first['posts'][0]['shortcode'], 'AbCd000')
                second = await browser.page('creator', first['cursor'])
                self.assertEqual([p['shortcode'] for p in second['posts']], ['AbCd012', 'AbCd013'])
                self.assertEqual(second['cursor'], '')
                with self.assertRaises(ValueError):
                    await browser.page('creator', first['cursor'])
            asyncio.run(run())

    def test_instagram_rejection_has_actionable_message(self) -> None:
        with patch.object(profiles, '_loader', side_effect=profiles.instaloader.exceptions.ConnectionException('private diagnostics')):
            with self.assertRaisesRegex(profiles.ProfileLookupError, 'reconnect Instagram'):
                asyncio.run(profiles.ProfileBrowser().page('creator'))

    def test_thumbnail_rejects_non_cdn_and_plain_http_without_fetch(self) -> None:
        with patch.object(profiles.requests, 'get') as fetch:
            self.assertFalse(profiles._cache_thumbnail('AbCd001', 'http://a.cdninstagram.com/x'))
            self.assertFalse(profiles._cache_thumbnail('AbCd001', 'https://127.0.0.1/x'))
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
