from pathlib import Path

from deploy.backfill_album_tags import backfill
from telegram_media.database import Database


def media_values():
    return {
        "kind": "video", "telegram_chat_id": 7, "telegram_message_id": 42,
        "telegram_file_id": "file-unique", "grouped_id": None, "source_name": "Source",
        "caption": "sample caption", "original_name": "sample.mp4", "mime_type": "video/mp4",
        "size_bytes": 1234, "width": 1920, "height": 1080, "duration_seconds": 12,
    }


def test_media_lifecycle(tmp_path: Path):
    db = Database(tmp_path / "media.db")
    try:
        media_id, status, duplicate = db.begin_media(media_values())
        assert not duplicate and status == "downloading"
        assert db.begin_media(media_values())[2]
        db.mark_ready(media_id, {
            "stored_name": "file.mp4", "relative_path": "video/2026/09/file.mp4",
            "thumbnail_path": "1.jpg", "size_bytes": 1234, "width": 1920,
            "height": 1080, "duration_seconds": 12,
        })
        assert db.list_media(kind="video", query="sample", favorite=False, trash=False, page=1, page_size=30)["total"] == 1
        assert db.stats()["videos"] == 1
        assert db.set_favorite(media_id, True)
        assert db.list_media(kind=None, query="", favorite=True, trash=False, page=1, page_size=30)["total"] == 1
        assert db.trash(media_id)
        assert db.list_media(kind=None, query="", favorite=False, trash=True, page=1, page_size=30)["total"] == 1
        assert db.restore(media_id)
    finally:
        db.close()


def test_login_limits_and_sessions(tmp_path: Path):
    db = Database(tmp_path / "media.db")
    try:
        for _ in range(8):
            db.record_login_failure("127.0.0.1")
        assert not db.login_allowed("127.0.0.1")
        db.clear_login_failures("127.0.0.1")
        assert db.login_allowed("127.0.0.1")
        db.create_session("hash", 4_102_444_800)
        assert db.valid_session("hash")
        db.delete_session("hash")
        assert not db.valid_session("hash")
    finally:
        db.close()


def test_tags_filter_and_bulk_operations(tmp_path: Path):
    db = Database(tmp_path / "media.db")
    try:
        first, _, _ = db.begin_media(media_values())
        second_values = {**media_values(), "telegram_message_id": 43, "telegram_file_id": "second"}
        second, _, _ = db.begin_media(second_values)
        ready = {"stored_name": "file.mp4", "relative_path": "video/2026/09/file.mp4", "thumbnail_path": None,
                 "size_bytes": 1234, "width": 1920, "height": 1080, "duration_seconds": 12}
        db.mark_ready(first, ready)
        db.mark_ready(second, {**ready, "stored_name": "second.mp4", "relative_path": "video/2026/09/second.mp4"})
        tutorial = db.create_tag("教程", "#112233")
        db.set_media_tags(first, [tutorial["id"]])
        assert db.list_media(kind=None, query="", favorite=False, trash=False, page=1, page_size=30, tag="教程")["total"] == 1
        assert db.get_media(first)["tags"][0]["name"] == "教程"
        db.add_tag_names(second, ["教程", "收藏夹"])
        assert {tag["name"] for tag in db.get_media(second)["tags"]} == {"教程", "收藏夹"}
        collection = next(tag for tag in db.list_tags() if tag["name"] == "收藏夹")
        db.bulk_media_tags([first], [collection["id"]], "add")
        assert {tag["name"] for tag in db.get_media(first)["tags"]} == {"教程", "收藏夹"}
        db.bulk_media_tags([first, second], [tutorial["id"]], "remove")
        assert db.list_media(kind=None, query="", favorite=False, trash=False, page=1, page_size=30, tag="教程")["total"] == 0
    finally:
        db.close()


def test_album_tags_are_applied_to_every_group_member(tmp_path: Path):
    db = Database(tmp_path / "media.db")
    try:
        first_values = {**media_values(), "grouped_id": "album-1", "caption": "旅程 #日本 #美食"}
        first, _, _ = db.begin_media(first_values)
        second, _, _ = db.begin_media({
            **first_values, "telegram_message_id": 43, "telegram_file_id": "album-second", "caption": None,
        })
        unrelated, _, _ = db.begin_media({
            **first_values, "telegram_message_id": 44, "telegram_file_id": "other-album",
            "grouped_id": "album-2", "caption": None,
        })

        names = []
        for caption in db.group_captions(7, "album-1"):
            from telegram_media.bot import extract_hashtags
            names.extend(extract_hashtags(caption))
        db.add_tag_names(second, names, telegram_chat_id=7, grouped_id="album-1")

        assert {tag["name"] for tag in db.get_media(first)["tags"]} == {"日本", "美食"}
        assert {tag["name"] for tag in db.get_media(second)["tags"]} == {"日本", "美食"}
        assert db.get_media(unrelated)["tags"] == []
    finally:
        db.close()


def test_late_album_member_inherits_existing_caption_tags(tmp_path: Path):
    db = Database(tmp_path / "media.db")
    try:
        first_values = {**media_values(), "grouped_id": "album-late", "caption": "说明 #合集"}
        first, _, _ = db.begin_media(first_values)
        db.add_tag_names(first, ["合集"], telegram_chat_id=7, grouped_id="album-late")

        late, _, _ = db.begin_media({
            **first_values, "telegram_message_id": 45, "telegram_file_id": "late-member", "caption": None,
        })
        db.add_tag_names(
            late,
            ["合集"],
            telegram_chat_id=7,
            grouped_id="album-late",
        )

        assert {tag["name"] for tag in db.get_media(first)["tags"]} == {"合集"}
        assert {tag["name"] for tag in db.get_media(late)["tags"]} == {"合集"}
    finally:
        db.close()


def test_backfill_repairs_existing_partially_tagged_album(tmp_path: Path):
    database_path = tmp_path / "media.db"
    db = Database(database_path)
    try:
        first_values = {**media_values(), "grouped_id": "existing-album", "caption": "说明 #旧相册"}
        first, _, _ = db.begin_media(first_values)
        second, _, _ = db.begin_media({
            **first_values, "telegram_message_id": 46, "telegram_file_id": "existing-second", "caption": None,
        })
        db.add_tag_names(first, ["旧相册"])
        assert db.get_media(second)["tags"] == []
    finally:
        db.close()

    assert backfill(database_path) == (1, 1)

    db = Database(database_path)
    try:
        assert {tag["name"] for tag in db.get_media(first)["tags"]} == {"旧相册"}
        assert {tag["name"] for tag in db.get_media(second)["tags"]} == {"旧相册"}
    finally:
        db.close()


def test_custom_albums_and_bulk_media_actions(tmp_path: Path):
    db = Database(tmp_path / "media.db")
    try:
        first, _, _ = db.begin_media(media_values())
        second, _, _ = db.begin_media({
            **media_values(), "telegram_message_id": 47, "telegram_file_id": "album-organizer-second",
        })
        ready = {"stored_name": "file.mp4", "relative_path": "video/2026/09/file.mp4", "thumbnail_path": None,
                 "size_bytes": 1234, "width": 1920, "height": 1080, "duration_seconds": 12}
        db.mark_ready(first, ready)
        db.mark_ready(second, {**ready, "stored_name": "second.mp4", "relative_path": "video/2026/09/second.mp4"})

        album = db.create_album("旅行", "2026 旅行记录")
        db.set_media_albums(first, [album["id"]])
        db.bulk_media_albums([second], [album["id"]], "add")
        result = db.list_media(kind=None, query="", favorite=False, trash=False, page=1, page_size=30, album_id=album["id"])
        assert result["total"] == 2
        assert all(item["albums"][0]["name"] == "旅行" for item in result["items"])
        assert db.list_albums()[0]["mediaCount"] == 2

        assert db.bulk_media_action([first, second], "favorite") == 2
        assert db.list_media(kind=None, query="", favorite=True, trash=False, page=1, page_size=30)["total"] == 2
        assert db.bulk_media_action([first, second], "trash") == 2
        assert db.bulk_media_action([first, second], "restore") == 2
        assert db.update_album(album["id"], "旅程", "更新说明")
        assert db.delete_album(album["id"])
        assert db.get_media(first)["albums"] == []
    finally:
        db.close()

