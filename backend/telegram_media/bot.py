from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any

from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeVideo

from .config import Settings
from .database import Database
from .storage import destination_for, enough_disk_space, finalize_download, resolve_inside


logger = logging.getLogger(__name__)


HASHTAG_PATTERN = re.compile(r"(?<!\w)#([\w\u3400-\u9fff-]{1,32})", re.UNICODE)


def extract_hashtags(caption: str | None) -> list[str]:
    return list(dict.fromkeys(HASHTAG_PATTERN.findall(caption or "")))


def _document_attributes(message: Any) -> tuple[str | None, int | None, int | None, float | None]:
    name = None
    width = height = None
    duration = None
    document = getattr(message, "document", None)
    for attribute in getattr(document, "attributes", []) or []:
        if isinstance(attribute, DocumentAttributeFilename):
            name = attribute.file_name
        elif isinstance(attribute, DocumentAttributeVideo):
            width, height, duration = attribute.w, attribute.h, float(attribute.duration)
    return name, width, height, duration


def describe_media(message: Any) -> dict[str, Any] | None:
    file = getattr(message, "file", None)
    if not file:
        return None
    original_name, width, height, duration = _document_attributes(message)
    mime_type = getattr(file, "mime_type", None)
    if getattr(message, "photo", None):
        kind = "image"
        media_id = str(message.photo.id)
        original_name = original_name or f"photo-{message.id}.jpg"
        mime_type = mime_type or "image/jpeg"
    elif getattr(message, "video", None) or (mime_type or "").startswith("video/"):
        kind = "video"
        media_id = str(message.document.id)
        original_name = original_name or f"video-{message.id}{getattr(file, 'ext', '.mp4') or '.mp4'}"
    elif getattr(message, "document", None):
        kind = "image" if (mime_type or "").startswith("image/") else "document"
        media_id = str(message.document.id)
        original_name = original_name or f"document-{message.id}{getattr(file, 'ext', '') or ''}"
    else:
        return None
    return {
        "kind": kind,
        "telegram_chat_id": int(message.chat_id),
        "telegram_message_id": int(message.id),
        "telegram_file_id": media_id,
        "grouped_id": str(message.grouped_id) if message.grouped_id else None,
        "caption": message.message or None,
        "original_name": original_name,
        "mime_type": mime_type,
        "size_bytes": int(getattr(file, "size", 0) or 0),
        "width": width,
        "height": height,
        "duration_seconds": duration,
    }


async def _source_name(message: Any) -> str | None:
    forward = getattr(message, "forward", None)
    if forward:
        if getattr(forward, "from_name", None):
            return forward.from_name
        if getattr(forward, "chat", None):
            return getattr(forward.chat, "title", None) or getattr(forward.chat, "username", None)
        if getattr(forward, "sender", None):
            return getattr(forward.sender, "username", None) or getattr(forward.sender, "first_name", None)
    sender = await message.get_sender()
    return getattr(sender, "username", None) or getattr(sender, "first_name", None)


class TelegramWorker:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self.client: TelegramClient | None = None
        self.download_lock = asyncio.Semaphore(settings.download_concurrency)

    async def start(self) -> None:
        if not self.settings.telegram_enabled:
            logger.warning("Telegram receiver is disabled")
            return
        self.client = TelegramClient(
            str(self.settings.telegram_session_path),
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash,
            connection_retries=10,
            retry_delay=5,
        )
        self.client.add_event_handler(self._handle_message, events.NewMessage(incoming=True))
        await self.client.start(bot_token=self.settings.telegram_bot_token)
        identity = await self.client.get_me()
        logger.info("Telegram MTProto bot started as @%s", getattr(identity, "username", "unknown"))

    async def stop(self) -> None:
        if self.client:
            await self.client.disconnect()

    async def _handle_message(self, event: Any) -> None:
        sender_id = int(event.sender_id or 0)
        if sender_id not in self.settings.telegram_allowed_user_ids:
            logger.warning("Rejected Telegram user %s", sender_id)
            await event.respond("⛔ 你没有权限使用这个转存机器人。")
            return
        item = describe_media(event.message)
        if not item:
            await event.respond("请发送或转发图片、视频或文件。")
            return
        item["source_name"] = await _source_name(event.message)
        expected_size = int(item.get("size_bytes") or 0)
        if expected_size > self.settings.max_file_bytes:
            await event.respond("❌ 文件超过 2GB 上限。")
            return
        if not enough_disk_space(self.settings, expected_size):
            await event.respond("❌ VPS 可用空间不足，已保留安全空间，暂不下载。")
            return

        media_id, status, duplicate = self.db.begin_media(item)
        if duplicate:
            await event.respond(f"✅ 已经转存过（媒体 #{media_id}，状态：{status}）。")
            return

        status_message = await event.respond("⏳ 已加入转存队列…")
        async with self.download_lock:
            temporary = resolve_inside(self.settings.temp_dir, f"{media_id}.part")
            destination, relative_path, stored_name = destination_for(
                self.settings, media_id, item["kind"], item.get("original_name"), item.get("mime_type")
            )
            last_update = 0.0
            last_percent = -1

            async def progress(current: int, total: int) -> None:
                nonlocal last_update, last_percent
                now = time.monotonic()
                percent = int(current * 100 / total) if total else 0
                if now - last_update < 8 and percent < last_percent + 10:
                    return
                last_update, last_percent = now, percent
                try:
                    await status_message.edit(f"⏳ 正在转存：{percent}% ({current / 1024 / 1024:.1f} MB)")
                except Exception:
                    logger.debug("Could not update Telegram progress", exc_info=True)

            try:
                temporary.unlink(missing_ok=True)
                await event.message.download_media(file=str(temporary), progress_callback=progress)
                if not temporary.exists():
                    raise RuntimeError("Telegram download did not create a file")
                await finalize_download(
                    self.settings, self.db, media_id, temporary, destination, relative_path, stored_name, item["kind"]
                )
                tag_names = extract_hashtags(item.get("caption"))
                if item.get("grouped_id"):
                    for caption in self.db.group_captions(item["telegram_chat_id"], item["grouped_id"]):
                        tag_names.extend(extract_hashtags(caption))
                self.db.add_tag_names(
                    media_id,
                    tag_names,
                    telegram_chat_id=item["telegram_chat_id"],
                    grouped_id=item.get("grouped_id"),
                )
                await status_message.edit(f"✅ 转存成功（媒体 #{media_id}）")
            except Exception as error:
                temporary.unlink(missing_ok=True)
                destination.unlink(missing_ok=True)
                self.db.mark_failed(media_id, str(error))
                logger.exception("Telegram download failed for media %s", media_id)
                await status_message.edit(f"❌ 转存失败：{str(error)[:180]}")

