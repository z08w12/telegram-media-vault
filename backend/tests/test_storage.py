from pathlib import Path

import pytest

from telegram_media.storage import resolve_inside, safe_extension


def test_safe_extension_prefers_known_mime_type():
    assert safe_extension("file.exe", "image/jpeg") == ".jpg"
    assert safe_extension("clip.MP4", "application/octet-stream") == ".mp4"
    assert safe_extension("bad.exe?", "application/octet-stream") == ".bin"


def test_resolve_inside_blocks_traversal(tmp_path: Path):
    assert resolve_inside(tmp_path, "video/file.mp4") == tmp_path / "video" / "file.mp4"
    with pytest.raises(ValueError):
        resolve_inside(tmp_path, "../secret")

