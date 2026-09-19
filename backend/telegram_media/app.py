from __future__ import annotations

import asyncio
import re
import sqlite3
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import quote

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .bot import TelegramWorker
from .config import Settings
from .database import Database
from .security import new_session_token, token_hash, verify_password
from .storage import cleanup_expired_trash, content_type, permanently_delete, resolve_inside


SESSION_SECONDS = 7 * 24 * 60 * 60


class LoginBody(BaseModel):
    password: str


class FavoriteBody(BaseModel):
    favorite: bool


class TagBody(BaseModel):
    name: str
    color: str = "#55c6f5"


class MediaTagsBody(BaseModel):
    tag_ids: list[int]


class BulkTagsBody(BaseModel):
    media_ids: list[int]
    tag_ids: list[int]
    action: str


class AlbumBody(BaseModel):
    name: str
    description: str = ""


class MediaAlbumsBody(BaseModel):
    album_ids: list[int]


class BulkAlbumsBody(BaseModel):
    media_ids: list[int]
    album_ids: list[int]
    action: str


class BulkMediaBody(BaseModel):
    media_ids: list[int]
    action: str


def clean_tag(body: TagBody) -> tuple[str, str]:
    name = body.name.strip().lstrip("#")[:32]
    if not name or any(character.isspace() for character in name):
        raise HTTPException(status_code=422, detail="标签名不能为空或包含空格")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", body.color):
        raise HTTPException(status_code=422, detail="标签颜色格式无效")
    return name, body.color.lower()


def clean_album(body: AlbumBody) -> tuple[str, str]:
    name = body.name.strip()[:64]
    if not name:
        raise HTTPException(status_code=422, detail="相册名不能为空")
    return name, body.description.strip()[:500]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_directories()
    db = Database(settings.database_path)
    bot = TelegramWorker(settings, db)

    async def cleanup_loop() -> None:
        while True:
            await cleanup_expired_trash(settings, db)
            await asyncio.sleep(24 * 60 * 60)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await bot.start()
        cleanup_task = asyncio.create_task(cleanup_loop())
        try:
            yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            await bot.stop()
            db.close()

    app = FastAPI(title="Telegram Media Vault", version="1.0.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException):
        return JSONResponse({"error": error.detail}, status_code=error.status_code, headers=error.headers)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != settings.public_origin:
                return JSONResponse({"error": "请求来源无效"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def require_session(tmv_session: str | None = Cookie(default=None)) -> str:
        if not tmv_session or not db.valid_session(token_hash(tmv_session, settings.session_secret)):
            raise HTTPException(status_code=401, detail="请先登录")
        return tmv_session

    @app.get("/api/health")
    async def health():
        return {"ok": True, "telegramEnabled": settings.telegram_enabled}

    @app.post("/api/auth/login")
    async def login(body: LoginBody, request: Request, response: Response):
        ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
        if not db.login_allowed(ip):
            raise HTTPException(status_code=429, detail="尝试次数过多，请稍后再试")
        if not verify_password(body.password, settings.admin_password_hash):
            db.record_login_failure(ip)
            raise HTTPException(status_code=401, detail="密码错误")
        db.clear_login_failures(ip)
        token = new_session_token()
        db.create_session(token_hash(token, settings.session_secret), int(time.time()) + SESSION_SECONDS)
        response.set_cookie(
            "tmv_session", token, max_age=SESSION_SECONDS, path=settings.cookie_path,
            secure=True, httponly=True, samesite="strict",
        )
        return {"ok": True}

    @app.post("/api/auth/logout")
    async def logout(response: Response, session: str = Depends(require_session)):
        db.delete_session(token_hash(session, settings.session_secret))
        response.delete_cookie("tmv_session", path=settings.cookie_path)
        return {"ok": True}

    @app.get("/api/auth/session")
    async def session(_: str = Depends(require_session)):
        return {"authenticated": True}

    @app.get("/api/stats")
    async def stats(_: str = Depends(require_session)):
        return db.stats()

    @app.get("/api/media")
    async def list_media(
        kind: str | None = None, q: str = "", favorite: bool = False, trash: bool = False,
        tag: str = "", album: int | None = None, page: int = 1, pageSize: int = 30,
        _: str = Depends(require_session),
    ):
        return db.list_media(
            kind=kind, query=q.strip()[:100], favorite=favorite, trash=trash,
            tag=tag.strip()[:32], album_id=album, page=max(1, page), page_size=min(100, max(1, pageSize)),
        )

    @app.get("/api/tags")
    async def list_tags(_: str = Depends(require_session)):
        return {"items": db.list_tags()}

    @app.post("/api/tags", status_code=201)
    async def create_tag(body: TagBody, _: str = Depends(require_session)):
        name, color = clean_tag(body)
        try:
            return db.create_tag(name, color)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="标签已存在")

    @app.patch("/api/tags/{tag_id}")
    async def update_tag(tag_id: int, body: TagBody, _: str = Depends(require_session)):
        name, color = clean_tag(body)
        try:
            if not db.update_tag(tag_id, name, color):
                raise HTTPException(status_code=404, detail="标签不存在")
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="标签已存在")
        return {"ok": True}

    @app.delete("/api/tags/{tag_id}")
    async def delete_tag(tag_id: int, _: str = Depends(require_session)):
        if not db.delete_tag(tag_id):
            raise HTTPException(status_code=404, detail="标签不存在")
        return {"ok": True}

    @app.put("/api/media/{media_id}/tags")
    async def set_media_tags(media_id: int, body: MediaTagsBody, _: str = Depends(require_session)):
        media_or_404(media_id)
        db.set_media_tags(media_id, body.tag_ids[:100])
        return {"ok": True, "tags": db.get_media(media_id)["tags"]}

    @app.post("/api/media/bulk-tags")
    async def bulk_media_tags(body: BulkTagsBody, _: str = Depends(require_session)):
        if body.action not in {"add", "remove"}:
            raise HTTPException(status_code=422, detail="批量操作无效")
        if not body.media_ids or not body.tag_ids:
            raise HTTPException(status_code=422, detail="请选择媒体和标签")
        db.bulk_media_tags(body.media_ids[:500], body.tag_ids[:100], body.action)
        return {"ok": True}

    @app.get("/api/albums")
    async def list_albums(_: str = Depends(require_session)):
        return {"items": db.list_albums()}

    @app.post("/api/albums", status_code=201)
    async def create_album(body: AlbumBody, _: str = Depends(require_session)):
        name, description = clean_album(body)
        try:
            return db.create_album(name, description)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="相册已存在")

    @app.patch("/api/albums/{album_id}")
    async def update_album(album_id: int, body: AlbumBody, _: str = Depends(require_session)):
        name, description = clean_album(body)
        try:
            if not db.update_album(album_id, name, description):
                raise HTTPException(status_code=404, detail="相册不存在")
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="相册已存在")
        return {"ok": True}

    @app.delete("/api/albums/{album_id}")
    async def delete_album(album_id: int, _: str = Depends(require_session)):
        if not db.delete_album(album_id):
            raise HTTPException(status_code=404, detail="相册不存在")
        return {"ok": True}

    @app.put("/api/media/{media_id}/albums")
    async def set_media_albums(media_id: int, body: MediaAlbumsBody, _: str = Depends(require_session)):
        media_or_404(media_id)
        db.set_media_albums(media_id, body.album_ids[:100])
        return {"ok": True, "albums": db.get_media(media_id)["albums"]}

    @app.post("/api/media/bulk-albums")
    async def bulk_media_albums(body: BulkAlbumsBody, _: str = Depends(require_session)):
        if body.action not in {"add", "remove"}:
            raise HTTPException(status_code=422, detail="批量操作无效")
        if not body.media_ids or not body.album_ids:
            raise HTTPException(status_code=422, detail="请选择媒体和相册")
        db.bulk_media_albums(body.media_ids[:500], body.album_ids[:100], body.action)
        return {"ok": True}

    @app.post("/api/media/bulk")
    async def bulk_media(body: BulkMediaBody, _: str = Depends(require_session)):
        media_ids = list(dict.fromkeys(body.media_ids[:500]))
        if not media_ids:
            raise HTTPException(status_code=422, detail="请选择媒体")
        if body.action in {"favorite", "unfavorite", "trash", "restore"}:
            return {"ok": True, "affected": db.bulk_media_action(media_ids, body.action)}
        if body.action == "permanent":
            affected = 0
            for media_id in media_ids:
                record = db.get_media(media_id)
                if record and record["status"] == "ready" and record["deleted_at"]:
                    await permanently_delete(settings, db, record)
                    affected += 1
            return {"ok": True, "affected": affected}
        raise HTTPException(status_code=422, detail="批量操作无效")

    def media_or_404(media_id: int, *, include_deleted: bool = False):
        record = db.get_media(media_id)
        if not record or record["status"] != "ready" or (record["deleted_at"] and not include_deleted):
            raise HTTPException(status_code=404, detail="媒体不存在")
        return record

    @app.get("/api/media/{media_id}")
    async def media_detail(media_id: int, _: str = Depends(require_session)):
        return media_or_404(media_id)

    def accelerated(record: dict, *, thumbnail: bool = False, download: bool = False) -> Response:
        if thumbnail and record.get("thumbnail_path"):
            internal_path = f"/_telegram_thumbnails/{quote(record['thumbnail_path'])}"
            mime = "image/jpeg"
        else:
            internal_path = f"/_telegram_media/{quote(record['relative_path'])}"
            mime = content_type(record)
        headers = {"X-Accel-Redirect": internal_path, "Cache-Control": "private, max-age=3600"}
        if download:
            name = quote(record.get("original_name") or record.get("stored_name") or "download")
            headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{name}"
        return Response(headers=headers, media_type=mime)

    @app.get("/api/media/{media_id}/content")
    async def media_content(media_id: int, _: str = Depends(require_session)):
        return accelerated(media_or_404(media_id))

    @app.get("/api/media/{media_id}/thumbnail")
    async def media_thumbnail(media_id: int, _: str = Depends(require_session)):
        return accelerated(media_or_404(media_id), thumbnail=True)

    @app.get("/api/media/{media_id}/download")
    async def media_download(media_id: int, _: str = Depends(require_session)):
        return accelerated(media_or_404(media_id), download=True)

    @app.patch("/api/media/{media_id}/favorite")
    async def favorite_media(media_id: int, body: FavoriteBody, _: str = Depends(require_session)):
        media_or_404(media_id)
        db.set_favorite(media_id, body.favorite)
        return {"ok": True}

    @app.delete("/api/media/{media_id}")
    async def trash_media(media_id: int, _: str = Depends(require_session)):
        media_or_404(media_id)
        db.trash(media_id)
        return {"ok": True}

    @app.post("/api/media/{media_id}/restore")
    async def restore_media(media_id: int, _: str = Depends(require_session)):
        media_or_404(media_id, include_deleted=True)
        db.restore(media_id)
        return {"ok": True}

    @app.delete("/api/media/{media_id}/permanent")
    async def permanently_delete_media(media_id: int, _: str = Depends(require_session)):
        record = media_or_404(media_id, include_deleted=True)
        if not record["deleted_at"]:
            raise HTTPException(status_code=409, detail="请先移至回收站")
        await permanently_delete(settings, db, record)
        return {"ok": True}

    @app.get("/{path:path}", include_in_schema=False)
    async def web(path: str):
        candidate = resolve_inside(settings.web_dir, path or "index.html")
        if candidate.is_file():
            return FileResponse(candidate)
        index = settings.web_dir / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend not built")

    return app

