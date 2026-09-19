from pathlib import Path

from fastapi.testclient import TestClient

from telegram_media.app import create_app
from telegram_media.config import Settings
from telegram_media.security import hash_password


def settings(tmp_path: Path) -> Settings:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>vault</h1>", encoding="utf-8")
    return Settings(
        data_dir=tmp_path / "data", web_dir=web, public_origin="https://testserver",
        cookie_path="/", admin_password_hash=hash_password("a long test password"),
        session_secret="test-secret-that-is-long-enough", telegram_enabled=False,
        telegram_api_id=None, telegram_api_hash=None, telegram_bot_token=None,
        telegram_allowed_user_ids=frozenset(), max_file_bytes=2_147_483_648,
        disk_reserve_bytes=1, trash_retention_days=30,
    )


def test_login_and_protected_media_flow(tmp_path: Path):
    app = create_app(settings(tmp_path))
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/api/media").status_code == 401
        assert client.post("/api/auth/login", json={"password": "wrong password"}).status_code == 401
        assert client.post("/api/auth/login", json={"password": "a long test password"}).status_code == 200
        assert client.get("/api/auth/session").status_code == 200
        db = app.state.db
        media_id, _, _ = db.begin_media({
            "kind": "video", "telegram_chat_id": 1, "telegram_message_id": 2,
            "telegram_file_id": "3", "original_name": "movie.mp4", "mime_type": "video/mp4",
            "size_bytes": 10,
        })
        db.mark_ready(media_id, {
            "stored_name": "movie.mp4", "relative_path": "video/2026/09/movie.mp4",
            "thumbnail_path": None, "size_bytes": 10, "width": 100, "height": 100,
            "duration_seconds": 1,
        })
        response = client.get(f"/api/media/{media_id}/content")
        assert response.status_code == 200
        assert response.headers["x-accel-redirect"] == "/_telegram_media/video/2026/09/movie.mp4"
        assert client.delete(f"/api/media/{media_id}").status_code == 200
        assert client.post(f"/api/media/{media_id}/restore").status_code == 200

        tag = client.post("/api/tags", json={"name": "旅行", "color": "#336699"})
        assert tag.status_code == 201
        tag_id = tag.json()["id"]
        assert client.put(f"/api/media/{media_id}/tags", json={"tag_ids": [tag_id]}).status_code == 200
        assert client.get("/api/media", params={"tag": "旅行"}).json()["total"] == 1
        assert client.post("/api/media/bulk-tags", json={"media_ids": [media_id], "tag_ids": [tag_id], "action": "remove"}).status_code == 200
        assert client.get("/api/media", params={"tag": "旅行"}).json()["total"] == 0

        album = client.post("/api/albums", json={"name": "精选", "description": "精选视频"})
        assert album.status_code == 201
        album_id = album.json()["id"]
        assert client.put(f"/api/media/{media_id}/albums", json={"album_ids": [album_id]}).status_code == 200
        assert client.get("/api/media", params={"album": album_id}).json()["total"] == 1
        assert client.post("/api/media/bulk", json={"media_ids": [media_id], "action": "favorite"}).json()["affected"] == 1
        assert client.post("/api/media/bulk", json={"media_ids": [media_id], "action": "trash"}).json()["affected"] == 1
        assert client.post("/api/media/bulk", json={"media_ids": [media_id], "action": "restore"}).json()["affected"] == 1
        assert client.delete(f"/api/albums/{album_id}").status_code == 200


def test_origin_protection(tmp_path: Path):
    app = create_app(settings(tmp_path))
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/auth/login", json={"password": "a long test password"},
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 403


def test_tag_validation_and_duplicates(tmp_path: Path):
    app = create_app(settings(tmp_path))
    with TestClient(app, base_url="https://testserver") as client:
        client.post("/api/auth/login", json={"password": "a long test password"})
        assert client.post("/api/tags", json={"name": "bad tag", "color": "#ffffff"}).status_code == 422
        assert client.post("/api/tags", json={"name": "安全", "color": "red"}).status_code == 422
        assert client.post("/api/tags", json={"name": "安全", "color": "#ffffff"}).status_code == 201
        assert client.post("/api/tags", json={"name": "安全", "color": "#ffffff"}).status_code == 409

