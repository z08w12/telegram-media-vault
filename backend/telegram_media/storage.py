from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .config import Settings
from .database import Database


SAFE_EXTENSION = re.compile(r"^\.[a-z0-9]{1,8}$")
MIME_EXTENSIONS = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/x-matroska": ".mkv", "video/webm": ".webm",
}


def safe_extension(file_name: str | None, mime_type: str | None) -> str:
    if mime_type in MIME_EXTENSIONS:
        return MIME_EXTENSIONS[mime_type]
    extension = Path(file_name or "").suffix.lower()
    return extension if SAFE_EXTENSION.fullmatch(extension) else ".bin"


def resolve_inside(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Invalid media path")
    return candidate


def enough_disk_space(settings: Settings, expected_size: int) -> bool:
    return shutil.disk_usage(settings.data_dir).free >= expected_size + settings.disk_reserve_bytes


async def _run_json(*command: str) -> dict[str, Any] | None:
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return None
        return json.loads(stdout)
    except (OSError, json.JSONDecodeError):
        return None


async def probe_media(file_path: Path) -> dict[str, Any]:
    data = await _run_json(
        "ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(file_path)
    )
    if not data:
        return {"width": None, "height": None, "duration_seconds": None}
    video = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), {})
    try:
        duration = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        duration = None
    return {"width": video.get("width"), "height": video.get("height"), "duration_seconds": duration}


async def create_thumbnail(source: Path, destination: Path, kind: str) -> bool:
    seek = ["-ss", "00:00:01"] if kind == "video" else []
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-threads", "1", *seek, "-i", str(source), "-frames:v", "1",
            "-vf", "scale=640:-2", "-q:v", "4", str(destination),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        return await process.wait() == 0
    except OSError:
        return False


def destination_for(settings: Settings, media_id: int, kind: str, original_name: str | None, mime_type: str | None) -> tuple[Path, str, str]:
    now = time.gmtime()
    relative_directory = Path(kind) / str(now.tm_year) / f"{now.tm_mon:02d}"
    stored_name = f"{media_id}-{uuid.uuid4().hex[:12]}{safe_extension(original_name, mime_type)}"
    relative_path = (relative_directory / stored_name).as_posix()
    destination = resolve_inside(settings.media_dir, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination, relative_path, stored_name


async def finalize_download(
    settings: Settings,
    db: Database,
    media_id: int,
    temporary: Path,
    destination: Path,
    relative_path: str,
    stored_name: str,
    kind: str,
) -> None:
    size = temporary.stat().st_size
    if size > settings.max_file_bytes:
        raise ValueError("Downloaded file exceeds the 2GB limit")
    os.replace(temporary, destination)
    details = await probe_media(destination)
    thumbnail_path = None
    if kind in {"image", "video"}:
        thumbnail_name = f"{media_id}.jpg"
        thumbnail = resolve_inside(settings.thumbnail_dir, thumbnail_name)
        if await create_thumbnail(destination, thumbnail, kind):
            thumbnail_path = thumbnail_name
    db.mark_ready(
        media_id,
        {
            "stored_name": stored_name, "relative_path": relative_path, "thumbnail_path": thumbnail_path,
            "size_bytes": size, **details,
        },
    )


async def permanently_delete(settings: Settings, db: Database, record: dict[str, Any]) -> None:
    if record.get("relative_path"):
        resolve_inside(settings.media_dir, record["relative_path"]).unlink(missing_ok=True)
    if record.get("thumbnail_path"):
        resolve_inside(settings.thumbnail_dir, record["thumbnail_path"]).unlink(missing_ok=True)
    db.delete_record(int(record["id"]))


async def cleanup_expired_trash(settings: Settings, db: Database) -> None:
    for record in db.expired_trash(settings.trash_retention_days):
        await permanently_delete(settings, db, record)


def content_type(record: dict[str, Any]) -> str:
    return record.get("mime_type") or mimetypes.guess_type(record.get("stored_name") or "")[0] or "application/octet-stream"

