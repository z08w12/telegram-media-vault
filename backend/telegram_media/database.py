from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK(kind IN ('image','video','document')),
    status TEXT NOT NULL CHECK(status IN ('downloading','ready','failed')),
    telegram_chat_id INTEGER NOT NULL,
    telegram_message_id INTEGER NOT NULL,
    telegram_file_id TEXT NOT NULL,
    grouped_id TEXT,
    source_name TEXT,
    caption TEXT,
    original_name TEXT,
    stored_name TEXT,
    relative_path TEXT,
    thumbnail_path TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    width INTEGER,
    height INTEGER,
    duration_seconds REAL,
    is_favorite INTEGER NOT NULL DEFAULT 0,
    deleted_at INTEGER,
    error_message TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(telegram_chat_id, telegram_message_id, telegram_file_id)
);
CREATE INDEX IF NOT EXISTS idx_media_created ON media(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_media_kind ON media(kind);
CREATE INDEX IF NOT EXISTS idx_media_deleted ON media(deleted_at);
CREATE INDEX IF NOT EXISTS idx_media_group ON media(telegram_chat_id, grouped_id);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    color TEXT NOT NULL DEFAULT '#55c6f5',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS media_tags (
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    PRIMARY KEY(media_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_media_tags_tag ON media_tags(tag_id, media_id);
CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS album_media (
    album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    PRIMARY KEY(album_id, media_id)
);
CREATE INDEX IF NOT EXISTS idx_album_media_media ON album_media(media_id, album_id);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS login_failures (
    ip TEXT PRIMARY KEY,
    failure_count INTEGER NOT NULL,
    first_failed_at INTEGER NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.connection = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA busy_timeout=30000")
            self.connection.executescript(SCHEMA)

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    def _execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self.lock:
            cursor = self.connection.execute(sql, parameters)
            self.connection.commit()
            return cursor

    def begin_media(self, values: dict[str, Any]) -> tuple[int, str, bool]:
        now = int(time.time())
        with self.lock:
            try:
                cursor = self.connection.execute(
                    """INSERT INTO media (
                        kind,status,telegram_chat_id,telegram_message_id,telegram_file_id,grouped_id,
                        source_name,caption,original_name,mime_type,size_bytes,width,height,duration_seconds,
                        created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        values["kind"], "downloading", values["telegram_chat_id"], values["telegram_message_id"],
                        values["telegram_file_id"], values.get("grouped_id"), values.get("source_name"),
                        values.get("caption"), values.get("original_name"), values.get("mime_type"),
                        values.get("size_bytes"), values.get("width"), values.get("height"),
                        values.get("duration_seconds"), now, now,
                    ),
                )
                self.connection.commit()
                return int(cursor.lastrowid), "downloading", False
            except sqlite3.IntegrityError:
                row = self.connection.execute(
                    "SELECT id,status FROM media WHERE telegram_chat_id=? AND telegram_message_id=? AND telegram_file_id=?",
                    (values["telegram_chat_id"], values["telegram_message_id"], values["telegram_file_id"]),
                ).fetchone()
                assert row is not None
                return int(row["id"]), str(row["status"]), True

    def mark_ready(self, media_id: int, values: dict[str, Any]) -> None:
        self._execute(
            """UPDATE media SET status='ready',stored_name=?,relative_path=?,thumbnail_path=?,size_bytes=?,
               width=COALESCE(?,width),height=COALESCE(?,height),duration_seconds=COALESCE(?,duration_seconds),
               error_message=NULL,updated_at=? WHERE id=?""",
            (
                values["stored_name"], values["relative_path"], values.get("thumbnail_path"),
                values["size_bytes"], values.get("width"), values.get("height"),
                values.get("duration_seconds"), int(time.time()), media_id,
            ),
        )

    def mark_failed(self, media_id: int, error: str) -> None:
        self._execute(
            "UPDATE media SET status='failed',error_message=?,updated_at=? WHERE id=?",
            (error[:1000], int(time.time()), media_id),
        )

    def get_media(self, media_id: int) -> dict[str, Any] | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
            result = dict(row) if row else None
            if result:
                result["tags"] = self._tags_for_media_ids([media_id]).get(media_id, [])
                result["albums"] = self._albums_for_media_ids([media_id]).get(media_id, [])
        return result

    def _albums_for_media_ids(self, media_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        if not media_ids:
            return {}
        placeholders = ",".join("?" for _ in media_ids)
        rows = self.connection.execute(
            f"""SELECT am.media_id,a.id,a.name,a.description FROM album_media am
                JOIN albums a ON a.id=am.album_id WHERE am.media_id IN ({placeholders})
                ORDER BY lower(a.name),a.id""",
            media_ids,
        ).fetchall()
        result: dict[int, list[dict[str, Any]]] = {media_id: [] for media_id in media_ids}
        for row in rows:
            result[int(row["media_id"])].append({
                "id": int(row["id"]), "name": row["name"], "description": row["description"],
            })
        return result

    def _tags_for_media_ids(self, media_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        if not media_ids:
            return {}
        placeholders = ",".join("?" for _ in media_ids)
        rows = self.connection.execute(
            f"""SELECT mt.media_id,t.id,t.name,t.color FROM media_tags mt
                JOIN tags t ON t.id=mt.tag_id WHERE mt.media_id IN ({placeholders})
                ORDER BY lower(t.name),t.id""",
            media_ids,
        ).fetchall()
        result: dict[int, list[dict[str, Any]]] = {media_id: [] for media_id in media_ids}
        for row in rows:
            result[int(row["media_id"])].append({"id": int(row["id"]), "name": row["name"], "color": row["color"]})
        return result

    def list_media(self, *, kind: str | None, query: str, favorite: bool, trash: bool, page: int, page_size: int, tag: str = "", album_id: int | None = None) -> dict[str, Any]:
        clauses = ["status='ready'", "deleted_at IS NOT NULL" if trash else "deleted_at IS NULL"]
        parameters: list[Any] = []
        if kind in {"image", "video", "document"}:
            clauses.append("kind=?")
            parameters.append(kind)
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(original_name LIKE ? ESCAPE '\\' OR caption LIKE ? ESCAPE '\\' OR source_name LIKE ? ESCAPE '\\')")
            parameters.extend([f"%{escaped}%"] * 3)
        if favorite:
            clauses.append("is_favorite=1")
        if tag:
            clauses.append("EXISTS (SELECT 1 FROM media_tags mt JOIN tags t ON t.id=mt.tag_id WHERE mt.media_id=media.id AND t.name=? COLLATE NOCASE)")
            parameters.append(tag)
        if album_id is not None:
            clauses.append("EXISTS (SELECT 1 FROM album_media am WHERE am.media_id=media.id AND am.album_id=?)")
            parameters.append(album_id)
        where = " AND ".join(clauses)
        with self.lock:
            total = int(self.connection.execute(f"SELECT count(*) FROM media WHERE {where}", parameters).fetchone()[0])
            rows = self.connection.execute(
                f"SELECT * FROM media WHERE {where} ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
            items = [dict(row) for row in rows]
            tags = self._tags_for_media_ids([int(item["id"]) for item in items])
            albums = self._albums_for_media_ids([int(item["id"]) for item in items])
            for item in items:
                item["tags"] = tags.get(int(item["id"]), [])
                item["albums"] = albums.get(int(item["id"]), [])
        return {"items": items, "total": total, "page": page, "pageSize": page_size}

    def list_tags(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.connection.execute(
                """SELECT t.id,t.name,t.color,count(mt.media_id) media_count
                   FROM tags t LEFT JOIN media_tags mt ON mt.tag_id=t.id
                   GROUP BY t.id ORDER BY lower(t.name),t.id"""
            ).fetchall()
        return [{"id": int(row["id"]), "name": row["name"], "color": row["color"], "mediaCount": int(row["media_count"])} for row in rows]

    def create_tag(self, name: str, color: str = "#55c6f5") -> dict[str, Any]:
        now = int(time.time())
        with self.lock:
            cursor = self.connection.execute(
                "INSERT INTO tags(name,color,created_at,updated_at) VALUES(?,?,?,?)", (name, color, now, now)
            )
            self.connection.commit()
            tag_id = int(cursor.lastrowid)
        return {"id": tag_id, "name": name, "color": color, "mediaCount": 0}

    def update_tag(self, tag_id: int, name: str, color: str) -> bool:
        return self._execute(
            "UPDATE tags SET name=?,color=?,updated_at=? WHERE id=?", (name, color, int(time.time()), tag_id)
        ).rowcount > 0

    def delete_tag(self, tag_id: int) -> bool:
        return self._execute("DELETE FROM tags WHERE id=?", (tag_id,)).rowcount > 0

    def set_media_tags(self, media_id: int, tag_ids: list[int]) -> None:
        now = int(time.time())
        unique_ids = sorted(set(tag_ids))
        with self.lock:
            self.connection.execute("DELETE FROM media_tags WHERE media_id=?", (media_id,))
            self.connection.executemany(
                "INSERT INTO media_tags(media_id,tag_id,created_at) SELECT ?,id,? FROM tags WHERE id=?",
                [(media_id, now, tag_id) for tag_id in unique_ids],
            )
            self.connection.commit()

    def bulk_media_tags(self, media_ids: list[int], tag_ids: list[int], action: str) -> None:
        now = int(time.time())
        pairs = [(media_id, tag_id) for media_id in sorted(set(media_ids)) for tag_id in sorted(set(tag_ids))]
        with self.lock:
            if action == "add":
                self.connection.executemany(
                    "INSERT OR IGNORE INTO media_tags(media_id,tag_id,created_at) SELECT ?,id,? FROM tags WHERE id=?",
                    [(media_id, now, tag_id) for media_id, tag_id in pairs],
                )
            else:
                self.connection.executemany("DELETE FROM media_tags WHERE media_id=? AND tag_id=?", pairs)
            self.connection.commit()

    def group_captions(self, telegram_chat_id: int, grouped_id: str) -> list[str]:
        with self.lock:
            rows = self.connection.execute(
                """SELECT caption FROM media
                   WHERE telegram_chat_id=? AND grouped_id=? AND caption IS NOT NULL AND caption<>''""",
                (telegram_chat_id, grouped_id),
            ).fetchall()
        return [str(row["caption"]) for row in rows]

    def add_tag_names(
        self,
        media_id: int,
        names: list[str],
        *,
        telegram_chat_id: int | None = None,
        grouped_id: str | None = None,
    ) -> None:
        now = int(time.time())
        clean_names = list(dict.fromkeys(name.strip().lstrip("#")[:32] for name in names if name.strip().lstrip("#")))
        with self.lock:
            if grouped_id is not None and telegram_chat_id is not None:
                rows = self.connection.execute(
                    "SELECT id FROM media WHERE telegram_chat_id=? AND grouped_id=?",
                    (telegram_chat_id, grouped_id),
                ).fetchall()
                media_ids = [int(row["id"]) for row in rows]
            else:
                media_ids = [media_id]
            for name in clean_names:
                self.connection.execute(
                    "INSERT OR IGNORE INTO tags(name,color,created_at,updated_at) VALUES(?,?,?,?)",
                    (name, "#55c6f5", now, now),
                )
                self.connection.executemany(
                    """INSERT OR IGNORE INTO media_tags(media_id,tag_id,created_at)
                       SELECT ?,id,? FROM tags WHERE name=? COLLATE NOCASE""",
                    [(target_media_id, now, name) for target_media_id in media_ids],
                )
            self.connection.commit()

    def list_albums(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.connection.execute(
                """SELECT a.id,a.name,a.description,count(am.media_id) media_count,
                          (SELECT am2.media_id FROM album_media am2 JOIN media m2 ON m2.id=am2.media_id
                           WHERE am2.album_id=a.id AND m2.deleted_at IS NULL AND m2.status='ready'
                           ORDER BY am2.created_at DESC,am2.media_id DESC LIMIT 1) cover_media_id
                   FROM albums a LEFT JOIN album_media am ON am.album_id=a.id
                   GROUP BY a.id ORDER BY a.updated_at DESC,a.id DESC"""
            ).fetchall()
        return [{
            "id": int(row["id"]), "name": row["name"], "description": row["description"],
            "mediaCount": int(row["media_count"]),
            "coverMediaId": int(row["cover_media_id"]) if row["cover_media_id"] is not None else None,
        } for row in rows]

    def create_album(self, name: str, description: str = "") -> dict[str, Any]:
        now = int(time.time())
        with self.lock:
            cursor = self.connection.execute(
                "INSERT INTO albums(name,description,created_at,updated_at) VALUES(?,?,?,?)",
                (name, description, now, now),
            )
            self.connection.commit()
        return {"id": int(cursor.lastrowid), "name": name, "description": description, "mediaCount": 0, "coverMediaId": None}

    def update_album(self, album_id: int, name: str, description: str) -> bool:
        return self._execute(
            "UPDATE albums SET name=?,description=?,updated_at=? WHERE id=?",
            (name, description, int(time.time()), album_id),
        ).rowcount > 0

    def delete_album(self, album_id: int) -> bool:
        return self._execute("DELETE FROM albums WHERE id=?", (album_id,)).rowcount > 0

    def set_media_albums(self, media_id: int, album_ids: list[int]) -> None:
        now = int(time.time())
        with self.lock:
            self.connection.execute("DELETE FROM album_media WHERE media_id=?", (media_id,))
            self.connection.executemany(
                "INSERT INTO album_media(album_id,media_id,created_at) SELECT id,?,? FROM albums WHERE id=?",
                [(media_id, now, album_id) for album_id in sorted(set(album_ids))],
            )
            self.connection.commit()

    def bulk_media_albums(self, media_ids: list[int], album_ids: list[int], action: str) -> None:
        now = int(time.time())
        pairs = [(album_id, media_id) for media_id in sorted(set(media_ids)) for album_id in sorted(set(album_ids))]
        with self.lock:
            if action == "add":
                self.connection.executemany(
                    "INSERT OR IGNORE INTO album_media(album_id,media_id,created_at) SELECT id,?,? FROM albums WHERE id=?",
                    [(media_id, now, album_id) for album_id, media_id in pairs],
                )
            else:
                self.connection.executemany("DELETE FROM album_media WHERE album_id=? AND media_id=?", pairs)
            self.connection.commit()

    def bulk_media_action(self, media_ids: list[int], action: str) -> int:
        unique_ids = sorted(set(media_ids))
        if not unique_ids:
            return 0
        placeholders = ",".join("?" for _ in unique_ids)
        now = int(time.time())
        statements = {
            "favorite": ("is_favorite=1,updated_at=?", "deleted_at IS NULL"),
            "unfavorite": ("is_favorite=0,updated_at=?", "deleted_at IS NULL"),
            "trash": ("deleted_at=?,updated_at=?", "deleted_at IS NULL"),
            "restore": ("deleted_at=NULL,updated_at=?", "deleted_at IS NOT NULL"),
        }
        assignment, condition = statements[action]
        time_parameters: tuple[Any, ...] = (now, now) if action == "trash" else (now,)
        return self._execute(
            f"UPDATE media SET {assignment} WHERE id IN ({placeholders}) AND status='ready' AND {condition}",
            (*time_parameters, *unique_ids),
        ).rowcount

    def set_favorite(self, media_id: int, favorite: bool) -> bool:
        return self._execute(
            "UPDATE media SET is_favorite=?,updated_at=? WHERE id=? AND deleted_at IS NULL",
            (1 if favorite else 0, int(time.time()), media_id),
        ).rowcount > 0

    def trash(self, media_id: int) -> bool:
        now = int(time.time())
        return self._execute(
            "UPDATE media SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at IS NULL", (now, now, media_id)
        ).rowcount > 0

    def restore(self, media_id: int) -> bool:
        return self._execute(
            "UPDATE media SET deleted_at=NULL,updated_at=? WHERE id=? AND deleted_at IS NOT NULL",
            (int(time.time()), media_id),
        ).rowcount > 0

    def delete_record(self, media_id: int) -> bool:
        return self._execute("DELETE FROM media WHERE id=? AND deleted_at IS NOT NULL", (media_id,)).rowcount > 0

    def expired_trash(self, days: int) -> list[dict[str, Any]]:
        cutoff = int(time.time()) - days * 86400
        with self.lock:
            rows = self.connection.execute("SELECT * FROM media WHERE deleted_at IS NOT NULL AND deleted_at<?", (cutoff,)).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, int]:
        with self.lock:
            row = self.connection.execute(
                """SELECT count(*) files,COALESCE(sum(size_bytes),0) bytes,
                   COALESCE(sum(kind='image'),0) images,COALESCE(sum(kind='video'),0) videos
                   FROM media WHERE status='ready' AND deleted_at IS NULL"""
            ).fetchone()
        return {key: int(row[key]) for key in ("files", "bytes", "images", "videos")}

    def create_session(self, hashed_token: str, expires_at: int) -> None:
        now = int(time.time())
        self._execute("DELETE FROM sessions WHERE expires_at<?", (now,))
        self._execute("INSERT INTO sessions(token_hash,created_at,expires_at) VALUES(?,?,?)", (hashed_token, now, expires_at))

    def valid_session(self, hashed_token: str) -> bool:
        now = int(time.time())
        with self.lock:
            row = self.connection.execute("SELECT 1 FROM sessions WHERE token_hash=? AND expires_at>?", (hashed_token, now)).fetchone()
        return row is not None

    def delete_session(self, hashed_token: str) -> None:
        self._execute("DELETE FROM sessions WHERE token_hash=?", (hashed_token,))

    def login_allowed(self, ip: str, *, max_failures: int = 8, window_seconds: int = 900) -> bool:
        now = int(time.time())
        with self.lock:
            row = self.connection.execute("SELECT failure_count,first_failed_at FROM login_failures WHERE ip=?", (ip,)).fetchone()
        return row is None or now - int(row["first_failed_at"]) > window_seconds or int(row["failure_count"]) < max_failures

    def record_login_failure(self, ip: str, *, window_seconds: int = 900) -> None:
        now = int(time.time())
        with self.lock:
            row = self.connection.execute("SELECT failure_count,first_failed_at FROM login_failures WHERE ip=?", (ip,)).fetchone()
            if row is None or now - int(row["first_failed_at"]) > window_seconds:
                self.connection.execute("INSERT OR REPLACE INTO login_failures VALUES(?,?,?)", (ip, 1, now))
            else:
                self.connection.execute("UPDATE login_failures SET failure_count=failure_count+1 WHERE ip=?", (ip,))
            self.connection.commit()

    def clear_login_failures(self, ip: str) -> None:
        self._execute("DELETE FROM login_failures WHERE ip=?", (ip,))

