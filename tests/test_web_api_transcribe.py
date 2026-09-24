import os
import unittest

from fastapi.testclient import TestClient

os.environ.setdefault("SUBTEXT_SERVER_KEY", "test")

from src.web.server import app  # noqa: E402


class FakeUploadService:
    def __init__(self):
        self.uploads = []

    async def transcribe_upload(self, file):
        self.uploads.append(file.filename)
        return {"text": "hello", "duration": 1.0, "latency": 0.1}

    def _touch_transcribe(self):
        return None


class ApiTranscribeTests(unittest.TestCase):
    def test_api_transcribe_accepts_a_file_without_a_url_field(self):
        with TestClient(app) as client:
            app.state.service = FakeUploadService()
            response = client.post(
                "/api/transcribe",
                files={"file": ("clip.m4a", b"audio", "audio/mp4")},
                headers={"x-subtext-key": "test"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["text"], "hello")
            self.assertEqual(app.state.service.uploads, ["clip.m4a"])


if __name__ == "__main__":
    unittest.main()
