# Telegram Media Vault

[English](README.md) | [简体中文](README.zh-CN.md)

一个私有、自托管的 Telegram 媒体库。把图片、视频、动画或文件发送给 Telegram Bot，服务会将文件保存到 VPS，并通过带登录保护的网页进行浏览、播放和管理。

项目通过 Telethon 使用 MTProto 接收文件，不受云端 Bot API 较小下载上限的限制。

## 功能

- Telegram 用户 ID 白名单与私人 Bot
- 通过 MTProto 接收图片、视频、动画和文件
- 向 Bot 发送公开 X/Twitter 帖子链接并转存其中的视频
- 单任务下载队列、进度反馈、重复检测和失败清理
- 可配置的 2 GB 文件上限和磁盘安全预留
- 临时文件完成后原子落盘，按类型、年份和月份保存
- 独立 SQLite 元数据数据库，启用 WAL 模式
- FFmpeg 缩略图和媒体信息提取
- 管理员密码保护的响应式网页媒体库
- 搜索、类型筛选、收藏、分页和空间统计
- 彩色标签、Telegram `#标签` 自动提取和组合筛选
- 自定义相册、封面、说明、成员管理和筛选
- 批量调整标签、相册、收藏和回收站状态
- 适配电脑和手机的图片全屏预览、上一张/下一张、键盘和滑动切换
- Nginx `X-Accel-Redirect` 鉴权传输和视频 Range 播放
- 回收站保留期和自动清理
- systemd 权限隔离、开机启动和故障重启

## 架构

```text
Telegram
   │  MTProto / Telethon
   ▼
FastAPI 接收服务 ─── SQLite 元数据
   │
   ├── 媒体文件
   ├── 缩略图
   └── Vue 网页
          │
          ▼
      Nginx + HTTPS
```

服务默认只监听 `127.0.0.1:9292`，由 Nginx 通过 `/telegram/` 提供公网访问。不要将 9292 端口直接开放到公网。

## 环境要求

- Python 3.12+ 的 Linux VPS
- Node.js 18+，以及用于前端构建的 pnpm 或 npm
- Nginx 和有效的 HTTPS 证书
- FFmpeg 与 ffprobe
- systemd
- 从 [my.telegram.org](https://my.telegram.org/) 获取的 API ID 和 API Hash
- 从 [BotFather](https://t.me/BotFather) 获取的 Bot Token

项目不依赖 Docker。

## 配置

复制 `.env.example` 并替换所有占位内容。不得把填写后的环境配置提交到仓库。

| 变量 | 用途 |
| --- | --- |
| `TELEGRAM_API_ID` | Telegram 应用 ID |
| `TELEGRAM_API_HASH` | Telegram 应用 Hash |
| `TELEGRAM_BOT_TOKEN` | BotFather Token |
| `TELEGRAM_ALLOWED_USER_IDS` | 允许使用 Bot 的 Telegram 数字用户 ID，英文逗号分隔 |
| `ADMIN_PASSWORD_HASH` | 网页管理员密码的 Scrypt 哈希 |
| `SESSION_SECRET` | 用于签名会话的长随机密钥 |
| `PUBLIC_ORIGIN` | HTTPS 来源，例如 `https://media.example.com` |
| `COOKIE_PATH` | 网页挂载路径，通常为 `/telegram/` |
| `DATA_DIR` | 数据库和媒体存储目录 |
| `WEB_DIR` | 前端构建产物目录 |

交互式配置命令不会将敏感输入写入 Shell 历史：

```bash
sudo telegram-media-configure
```

## 本地开发

后端：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
pytest backend/tests
```

前端：

```bash
pnpm install --frozen-lockfile
pnpm --dir apps/web build
```

## 部署

构建前端并把仓库暂存到服务器后运行：

```bash
sudo ./deploy/install.sh /path/to/staging https://media.example.com
sudo telegram-media-configure
```

要把项目提供的 Nginx location 加入已有 HTTPS 站点：

```bash
sudo python3 deploy/configure_nginx.py \
  --site /etc/nginx/sites-enabled/media.example.com \
  --server-name media.example.com
```

脚本会备份原配置、执行 `nginx -t`，验证失败时恢复备份。在生产环境运行前，请先审阅所有部署文件。

## 标签、相册和批量操作

- 在 Telegram 说明中加入 `#旅行 #教程`，系统会自动创建并关联标签。
- 同一个 Telegram 媒体组中的标签会同步到组内全部资源。
- 可以在网页创建相册，并把一个或多个媒体加入相册。
- 开启批量模式后，可以逐项选择或选择当前页，批量修改标签、相册、收藏或回收站状态。

## 公开 X 视频链接

向 Bot 发送公开的 `x.com/.../status/...` 或 `twitter.com/.../status/...` 链接，系统会按可用最高质量下载帖子中的原生视频并加入媒体库。Telegram 消息里附带的标签会应用到该帖子下载的全部视频。暂不支持私密、必须登录、已删除或受地区限制的帖子。本功能不转码视频；只有在音视频流需要合并时才由 FFmpeg 无损封装。

## 安全建议

- `/etc/telegram-media.env` 权限应保持为仅 root 可读（`0600`）。
- 9292 端口必须只绑定回环地址。
- 不要提交 Telegram Session、数据库、媒体、已填写的 `.env` 或私钥。
- 建议使用专用 Bot 和高强度管理员密码。
- 升级前备份数据目录。
- 安全漏洞请通过仓库的 GitHub Security 页面私下报告，不要创建公开 Issue。

仓库内的 ID、Token 和密码哈希均为不可用的占位示例，不是真实凭据。

## 数据与备份

运行数据与应用代码分开保存：

```text
/var/lib/telegram-media/
├── media/
├── thumbnails/
├── temp/
├── media.db
└── telegram-bot.session
```

请备份整个数据目录。最简单可靠的 SQLite 备份方式是短暂停止 `telegram-media.service` 后复制；也可以使用 SQLite Backup API 在线备份。

## 后续规划

- Cloudflare R2/S3 存储适配器与已有媒体迁移
- 自动转码为浏览器兼容视频
- 带有效期和密码保护的分享链接
- 高级元数据搜索和保存筛选条件
- 可选的多用户权限与两步验证

已实现功能清单见 [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)。
