import tempfile
import unittest
from pathlib import Path

from src.cli import SubtextApiClient, download_url_list, read_source_list, save_transcript_result


class FakeResponse:
    def __init__(self, *, json_data=None, chunks=None, headers=None):
        self._json_data = json_data or {}
        self._chunks = chunks or []
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_data

    def iter_content(self, chunk_size=1024 * 1024):
        yield from self._chunks


class FakeSession:
    def __init__(self, response):
        if isinstance(response, list):
            self.responses = response
        else:
            self.responses = [response]
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class CliClientTests(unittest.TestCase):
    def test_download_video_posts_to_running_service_and_saves_attachment(self):
        response = FakeResponse(
            chunks=[b"part-one", b"part-two"],
            headers={"content-disposition": 'attachment; filename="clip.mp4"'},
        )
        session = FakeSession(response)
        client = SubtextApiClient(
            "http://127.0.0.1:8000",
            api_key="secret",
            session=session,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            saved_path = client.download_video(
                "https://example.com/video",
                output_dir=Path(temp_dir),
            )
            saved_bytes = saved_path.read_bytes()

        self.assertEqual(saved_path.name, "clip.mp4")
        self.assertEqual(saved_bytes, b"part-onepart-two")
        self.assertEqual(session.calls[0][0], "http://127.0.0.1:8000/download-video")
        self.assertEqual(session.calls[0][1]["data"], {"url": "https://example.com/video"})
        self.assertEqual(session.calls[0][1]["headers"], {"x-subtext-key": "secret"})
        self.assertTrue(session.calls[0][1]["stream"])

    def test_transcribe_url_posts_to_running_service_and_saves_text(self):
        response = FakeResponse(json_data={"text": "hello from the transcript", "duration": 1.2})
        session = FakeSession(response)
        client = SubtextApiClient("http://127.0.0.1:8000/", session=session)

        result = client.transcribe_url("https://example.com/watch?v=abc")

        with tempfile.TemporaryDirectory() as temp_dir:
            saved_path = save_transcript_result(
                result,
                output_dir=Path(temp_dir),
                source_name="https://example.com/watch?v=abc",
            )
            saved_text = saved_path.read_text(encoding="utf-8")

        self.assertEqual(saved_path.name, "example.com_watch_v_abc.txt")
        self.assertEqual(saved_text, "hello from the transcript\n")
        self.assertEqual(session.calls[0][0], "http://127.0.0.1:8000/transcribe")
        self.assertEqual(session.calls[0][1]["data"], {"url": "https://example.com/watch?v=abc"})

    def test_read_source_list_skips_blanks_and_comments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "urls.txt"
            path.write_text(
                "# reviewed urls\n\nhttps://youtu.be/one\nhttps://youtu.be/two\n",
                encoding="utf-8",
            )

            sources = read_source_list(path)

        self.assertEqual(sources, ["https://youtu.be/one", "https://youtu.be/two"])

    def test_download_url_list_downloads_each_source(self):
        session = FakeSession(
            [
                FakeResponse(
                    chunks=[b"one"],
                    headers={"content-disposition": 'attachment; filename="clip.mp4"'},
                ),
                FakeResponse(
                    chunks=[b"two"],
                    headers={"content-disposition": 'attachment; filename="clip.mp4"'},
                ),
            ]
        )
        client = SubtextApiClient("http://127.0.0.1:8000", session=session)

        with tempfile.TemporaryDirectory() as temp_dir:
            saved_paths = download_url_list(
                client,
                ["https://youtu.be/one", "https://youtu.be/two"],
                output_dir=Path(temp_dir),
            )
            first = saved_paths[0].read_bytes()
            second = saved_paths[1].read_bytes()

        self.assertEqual([path.name for path in saved_paths], ["clip.mp4", "clip_1.mp4"])
        self.assertEqual(first, b"one")
        self.assertEqual(second, b"two")
        self.assertEqual(len(session.calls), 2)


if __name__ == "__main__":
    unittest.main()
