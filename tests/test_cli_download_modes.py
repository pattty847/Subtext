import unittest
from pathlib import Path

from src.cli import download_url_list


class DummyClient:
    def __init__(self):
        self.calls = []

    def download_video(self, url: str, *, output_dir: Path):
        self.calls.append(("video", url, output_dir))
        return output_dir / "video.out"

    def download_audio(self, url: str, *, output_dir: Path):
        self.calls.append(("audio", url, output_dir))
        return output_dir / "audio.out"


class CliDownloadModeTests(unittest.TestCase):
    def test_download_url_list_defaults_to_video(self):
        client = DummyClient()
        output_dir = Path("/tmp/subtext-test")

        saved = download_url_list(client, ["https://example.com/a"], output_dir=output_dir)

        self.assertEqual(saved, [output_dir / "video.out"])
        self.assertEqual(client.calls, [("video", "https://example.com/a", output_dir)])

    def test_download_url_list_can_use_audio_only(self):
        client = DummyClient()
        output_dir = Path("/tmp/subtext-test")

        saved = download_url_list(
            client,
            ["https://example.com/a", "https://example.com/b"],
            output_dir=output_dir,
            audio_only=True,
        )

        self.assertEqual(saved, [output_dir / "audio.out", output_dir / "audio.out"])
        self.assertEqual(
            client.calls,
            [
                ("audio", "https://example.com/a", output_dir),
                ("audio", "https://example.com/b", output_dir),
            ],
        )


if __name__ == "__main__":
    unittest.main()
