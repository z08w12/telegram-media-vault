from __future__ import annotations

import hashlib
import hmac
import grp
import json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


env = read_env(Path("/etc/telegram-media.env"))
data_dir = Path(env["DATA_DIR"])
base_url = env["PUBLIC_ORIGIN"].rstrip("/") + env.get("COOKIE_PATH", "/telegram/").rstrip("/")
database_path = data_dir / "media.db"
relative_path = "document/smoke/range-test.bin"
file_path = data_dir / "media" / relative_path
file_path.parent.mkdir(parents=True, exist_ok=True)
token = secrets.token_urlsafe(48)
hashed_token = hmac.new(env["SESSION_SECRET"].encode(), token.encode(), hashlib.sha256).hexdigest()
now = int(time.time())
connection = sqlite3.connect(database_path, timeout=30)
media_id = None

try:
    file_path.write_bytes(bytes(range(256)) * 4)
    os.chown(file_path, -1, grp.getgrnam("telegram-media").gr_gid)
    file_path.chmod(0o640)
    cursor = connection.execute(
        """INSERT INTO media (
            kind,status,telegram_chat_id,telegram_message_id,telegram_file_id,original_name,
            stored_name,relative_path,mime_type,size_bytes,created_at,updated_at
        ) VALUES ('document','ready',?,?,?,?,?,?,?,?,?,?)""",
        (-999999, -now, f"smoke-{now}", "range-test.bin", "range-test.bin", relative_path,
         "application/octet-stream", 1024, now, now),
    )
    media_id = int(cursor.lastrowid)
    connection.execute("INSERT INTO sessions(token_hash,created_at,expires_at) VALUES(?,?,?)", (hashed_token, now, now + 300))
    connection.commit()

    headers = {"Cookie": f"tmv_session={token}"}
    with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/media", headers=headers), timeout=15) as response:
        payload = json.loads(response.read())
        assert response.status == 200 and any(item["id"] == media_id for item in payload["items"])

    range_headers = {**headers, "Range": "bytes=10-25"}
    with urllib.request.urlopen(
        urllib.request.Request(f"{base_url}/api/media/{media_id}/content", headers=range_headers), timeout=15
    ) as response:
        body = response.read()
        assert response.status == 206
        assert len(body) == 16
        assert response.headers["Content-Range"] == "bytes 10-25/1024"
    print("PASS authenticated list=200 range=206 bytes=16")
finally:
    if media_id is not None:
        connection.execute("DELETE FROM media WHERE id=?", (media_id,))
    connection.execute("DELETE FROM sessions WHERE token_hash=?", (hashed_token,))
    connection.commit()
    connection.close()
    file_path.unlink(missing_ok=True)
