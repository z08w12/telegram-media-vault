from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


X_STATUS_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com)/"
    r"(?:(?:i/web|i)/status|[A-Za-z0-9_]{1,32}/status)/(?P<id>[0-9]{5,20})"
    r"(?:/(?:video|photo)/[0-9]+)?(?:[?#][^\s]*)?",
    re.IGNORECASE,
)


class XDownloadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class XPostReference:
    status_id: str
    url: str


@dataclass(frozen=True, slots=True)
class XDownloadedVideo:
    media_id: str
    path: Path
    title: str | None
    description: str | None
    uploader: str | None
    uploader_id: str | None
    webpage_url: str


def extract_x_status_url(text: str | None) -> XPostReference | None:
    match = X_STATUS_PATTERN.search(text or "")
    if not match:
        return None
    status_id = match.group("id")
    if int(status_id) > 9_223_372_036_854_775_807:
        return None
    return XPostReference(status_id=status_id, url=f"https://x.com/i/status/{status_id}")


def _entries(info: dict[str, Any]) -> list[dict[str, Any]]:
    nested = info.get("entries")
    if nested:
        result: list[dict[str, Any]] = []
        for entry in nested:
            if isinstance(entry, dict):
                result.extend(_entries(entry))
        return result
    return [info]


def download_public_x_post(
    reference: XPostReference,
    job_directory: Path,
    max_file_bytes: int,
    disk_reserve_bytes: int = 0,
) -> list[XDownloadedVideo]:
    job_directory.mkdir(parents=True, exist_ok=False)

    def check_limits(status: dict[str, Any]) -> None:
        if int(status.get("downloaded_bytes") or 0) > max_file_bytes:
            raise XDownloadError("X 视频超过 2GB 上限")
        if shutil.disk_usage(job_directory).free < disk_reserve_bytes:
            raise XDownloadError("VPS 可用空间不足，已停止下载")

    options: dict[str, Any] = {
        "allowed_extractors": [r"twitter"],
        "format": "bestvideo*+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": str(job_directory / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "playlistend": 4,
        "max_filesize": max_file_bytes,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 1,
        "overwrites": False,
        "ignoreerrors": True,
        "progress_hooks": [check_limits],
    }
    try:
        with YoutubeDL(options) as downloader:
            raw_info = downloader.extract_info(reference.url, download=True)
            info = downloader.sanitize_info(raw_info)
    except DownloadError as error:
        raise XDownloadError(str(error).removeprefix("ERROR: ")) from error
    except OSError as error:
        raise XDownloadError(f"下载器运行失败：{error}") from error

    if not isinstance(info, dict):
        raise XDownloadError("X 帖子没有返回可用的视频信息")
    videos: list[XDownloadedVideo] = []
    files = [path for path in job_directory.iterdir() if path.is_file() and path.suffix not in {".part", ".ytdl"}]
    for entry in _entries(info):
        media_id = str(entry.get("id") or "").strip()
        if not media_id:
            continue
        matching = sorted(path for path in files if path.stem == media_id)
        if not matching:
            continue
        path = matching[0].resolve()
        if job_directory.resolve() not in path.parents:
            raise XDownloadError("下载器返回了无效文件路径")
        if path.stat().st_size > max_file_bytes:
            raise XDownloadError("X 视频超过 2GB 上限")
        videos.append(XDownloadedVideo(
            media_id=media_id,
            path=path,
            title=entry.get("title"),
            description=entry.get("description"),
            uploader=entry.get("uploader"),
            uploader_id=entry.get("uploader_id"),
            webpage_url=entry.get("webpage_url") or reference.url,
        ))
    if not videos:
        raise XDownloadError("公开 X 帖子中没有可下载的视频，或视频超过大小限制")
    return videos
