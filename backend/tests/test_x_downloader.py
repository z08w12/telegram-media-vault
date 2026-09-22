from pathlib import Path

import telegram_media.x_downloader as x_downloader


def test_extract_x_status_url_accepts_x_and_twitter_links():
    first = x_downloader.extract_x_status_url("看看 https://x.com/example/status/1234567890?s=20 #收藏")
    second = x_downloader.extract_x_status_url("https://twitter.com/example/status/9876543210/video/1")
    assert first == x_downloader.XPostReference("1234567890", "https://x.com/i/status/1234567890")
    assert second == x_downloader.XPostReference("9876543210", "https://x.com/i/status/9876543210")


def test_extract_x_status_url_rejects_non_status_and_lookalike_hosts():
    assert x_downloader.extract_x_status_url("https://x.com/example") is None
    assert x_downloader.extract_x_status_url("https://x.com.example/status/123456") is None
    assert x_downloader.extract_x_status_url("file:///tmp/video.mp4") is None
    assert x_downloader.extract_x_status_url("https://x.com/example/status/99999999999999999999") is None


def test_download_public_x_post_collects_multiple_videos(monkeypatch, tmp_path: Path):
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def extract_info(self, url, download):
            assert url == "https://x.com/i/status/1234567890"
            assert download is True
            assert self.options["allowed_extractors"] == [r"twitter"]
            assert self.options["ignoreerrors"] is True
            output = Path(self.options["outtmpl"]).parent
            (output / "111.mp4").write_bytes(b"first")
            (output / "222.mp4").write_bytes(b"second")
            return {
                "entries": [
                    {"id": "111", "title": "First", "description": "#one", "uploader_id": "author"},
                    {"id": "222", "title": "Second", "description": "#two", "uploader": "Author"},
                ]
            }

        @staticmethod
        def sanitize_info(info):
            return info

    monkeypatch.setattr(x_downloader, "YoutubeDL", FakeYoutubeDL)
    reference = x_downloader.XPostReference("1234567890", "https://x.com/i/status/1234567890")
    videos = x_downloader.download_public_x_post(reference, tmp_path / "job", 1024)
    assert [video.media_id for video in videos] == ["111", "222"]
    assert [video.path.name for video in videos] == ["111.mp4", "222.mp4"]
