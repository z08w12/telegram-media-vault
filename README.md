# Telegram Media Vault

[English](README.md) | [简体中文](README.zh-CN.md)

A private, self-hosted media vault that receives photos, videos, animations, and documents through a Telegram bot, stores them on your VPS, and serves them through an authenticated web interface.

It uses Telethon over MTProto, so it is not restricted by the smaller download limit of the cloud Bot API.

## Features

- Telegram user ID allowlist and private bot access
- Photos, videos, animations, and document ingestion through MTProto
- Single-download queue, progress updates, duplicate detection, and failure cleanup
- Configurable 2 GB file limit and reserved disk-space threshold
- Atomic file writes and type/year/month storage layout
- SQLite metadata database with WAL mode
- FFmpeg thumbnails and media metadata probing
- Password-protected responsive web library
- Search, media-type filters, favorites, pagination, and storage statistics
- Color tags, automatic `#hashtag` extraction, and combined filters
- Custom albums with covers, descriptions, membership management, and filtering
- Bulk tag, album, favorite, trash, restore, and permanent-delete actions
- Responsive full-screen image viewer with buttons, keyboard navigation, and mobile swipe gestures
- Authenticated Nginx `X-Accel-Redirect` delivery and HTTP Range video playback
- Trash retention and automatic cleanup
- systemd service isolation and automatic restart

## Architecture

```text
Telegram
   │  MTProto / Telethon
   ▼
FastAPI receiver ─── SQLite metadata
   │
   ├── media files
   ├── thumbnails
   └── Vue web application
            │
            ▼
       Nginx + HTTPS
```

The application listens on `127.0.0.1:9292` by default. Nginx exposes it under `/telegram/`; the application port should not be opened to the public internet.

## Requirements

- Linux VPS with Python 3.12+
- Node.js 18+ and pnpm/npm for the frontend build
- Nginx and a valid HTTPS certificate
- FFmpeg and ffprobe
- systemd
- Telegram API ID and API Hash from [my.telegram.org](https://my.telegram.org/)
- A bot token from [BotFather](https://t.me/BotFather)

Docker is not required.

## Configuration

Copy `.env.example` and replace every placeholder. Never commit the populated environment file.

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_API_ID` | Telegram application ID |
| `TELEGRAM_API_HASH` | Telegram application hash |
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `TELEGRAM_ALLOWED_USER_IDS` | Comma-separated Telegram numeric user IDs |
| `ADMIN_PASSWORD_HASH` | Scrypt hash for the web administrator password |
| `SESSION_SECRET` | Long random session-signing secret |
| `PUBLIC_ORIGIN` | HTTPS origin, for example `https://media.example.com` |
| `COOKIE_PATH` | Web mount path, normally `/telegram/` |
| `DATA_DIR` | Database and media storage directory |
| `WEB_DIR` | Built frontend directory |

The interactive configuration command reads secrets without placing them in shell history:

```bash
sudo telegram-media-configure
```

## Development

Backend:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
pytest backend/tests
```

Frontend:

```bash
pnpm install --frozen-lockfile
pnpm --dir apps/web build
```

## Deployment

Build the frontend, stage the repository on the server, and run:

```bash
sudo ./deploy/install.sh /path/to/staging https://media.example.com
sudo telegram-media-configure
```

To add the supplied Nginx locations to an existing HTTPS server block:

```bash
sudo python3 deploy/configure_nginx.py \
  --site /etc/nginx/sites-enabled/media.example.com \
  --server-name media.example.com
```

The script backs up the site configuration, validates it with `nginx -t`, and restores the backup if validation fails. Review all deployment files before using them on a production server.

## Tags, albums, and bulk actions

- Add `#travel #tutorial` to a Telegram caption to create and attach tags automatically.
- Tags in a Telegram media group are propagated to every item in that group.
- Create albums from the web interface and assign one or many media items.
- Enable bulk mode to select individual cards or the current page, then update tags, albums, favorites, or trash state.

## Security

- Keep `/etc/telegram-media.env` readable only by root (`0600`).
- Keep port `9292` bound to loopback.
- Do not commit Telegram sessions, database files, media, generated `.env` files, or private keys.
- Use a dedicated bot and a strong administrator password.
- Back up the data directory before upgrades.
- Report vulnerabilities privately through the repository's GitHub Security tab rather than a public issue.

The repository contains placeholder IDs and tokens only. They are not usable credentials.

## Data and backup

Runtime data is stored separately from the application:

```text
/var/lib/telegram-media/
├── media/
├── thumbnails/
├── temp/
├── media.db
└── telegram-bot.session
```

Back up the entire data directory. For a simple consistent SQLite backup, briefly stop `telegram-media.service` before copying it, or use the SQLite backup API.

## Roadmap

- Cloudflare R2/S3 storage adapter and migration tooling
- Automatic browser-compatible video transcoding
- Expiring, password-protected share links
- Advanced metadata search and saved filters
- Optional multi-user roles and two-factor authentication

See [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) for the implemented feature checklist.
