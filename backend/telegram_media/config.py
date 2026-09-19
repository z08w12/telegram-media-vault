from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _positive_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    web_dir: Path
    public_origin: str
    cookie_path: str
    admin_password_hash: str
    session_secret: str
    telegram_enabled: bool
    telegram_api_id: int | None
    telegram_api_hash: str | None
    telegram_bot_token: str | None
    telegram_allowed_user_ids: frozenset[int]
    max_file_bytes: int
    disk_reserve_bytes: int
    trash_retention_days: int
    download_concurrency: int = 1

    @property
    def database_path(self) -> Path:
        return self.data_dir / "media.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def thumbnail_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "temp"

    @property
    def telegram_session_path(self) -> Path:
        return self.data_dir / "telegram-bot"

    @classmethod
    def from_env(cls) -> "Settings":
        telegram_enabled = os.environ.get("TELEGRAM_ENABLED", "true").lower() in {"1", "true", "yes"}
        allowed = frozenset(
            int(item.strip())
            for item in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
            if item.strip()
        )
        api_id = int(_required("TELEGRAM_API_ID")) if telegram_enabled else None
        api_hash = _required("TELEGRAM_API_HASH") if telegram_enabled else None
        bot_token = _required("TELEGRAM_BOT_TOKEN") if telegram_enabled else None
        if telegram_enabled and not allowed:
            raise RuntimeError("TELEGRAM_ALLOWED_USER_IDS must contain at least one user ID")
        return cls(
            data_dir=Path(os.environ.get("DATA_DIR", "/var/lib/telegram-media")).resolve(),
            web_dir=Path(os.environ.get("WEB_DIR", "/opt/telegram-media/web")).resolve(),
            public_origin=_required("PUBLIC_ORIGIN").rstrip("/"),
            cookie_path=os.environ.get("COOKIE_PATH", "/telegram/"),
            admin_password_hash=_required("ADMIN_PASSWORD_HASH"),
            session_secret=_required("SESSION_SECRET"),
            telegram_enabled=telegram_enabled,
            telegram_api_id=api_id,
            telegram_api_hash=api_hash,
            telegram_bot_token=bot_token,
            telegram_allowed_user_ids=allowed,
            max_file_bytes=_positive_int("MAX_FILE_BYTES", 2 * 1024 * 1024 * 1024),
            disk_reserve_bytes=_positive_int("DISK_RESERVE_BYTES", 5 * 1024 * 1024 * 1024),
            trash_retention_days=_positive_int("TRASH_RETENTION_DAYS", 30),
        )

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.media_dir, self.thumbnail_dir, self.temp_dir):
            directory.mkdir(parents=True, exist_ok=True)

