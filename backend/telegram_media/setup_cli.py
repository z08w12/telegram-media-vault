from __future__ import annotations

import getpass
import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

from .security import hash_password


ENV_PATH = Path("/etc/telegram-media.env")


def prompt(pattern: str, label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if re.fullmatch(pattern, value):
            return value
        print(f"格式无效，请重新输入 {label}。")


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("请使用 sudo 运行此配置命令。")

    print("Telegram Media Vault 安全配置")
    print("输入内容不会被保存到 shell 历史；管理员密码输入时不会显示。\n")
    api_id = prompt(r"[1-9][0-9]*", "Telegram API ID")
    api_hash = prompt(r"[0-9a-fA-F]{32}", "Telegram API Hash")
    bot_token = prompt(r"[0-9]+:[A-Za-z0-9_-]{20,}", "Bot Token")
    allowed_ids = prompt(r"[0-9]+(?:,[0-9]+)*", "允许使用 Bot 的 Telegram 用户 ID（多个用逗号分隔）")
    public_origin = prompt(
        r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?",
        "公网来源地址（例如 https://media.example.com）",
    )

    while True:
        password = getpass.getpass("网页管理员密码（至少 12 位）: ")
        confirmation = getpass.getpass("再次输入网页管理员密码: ")
        if password != confirmation:
            print("两次密码不一致，请重试。")
        elif len(password) < 12:
            print("密码不足 12 位，请重试。")
        else:
            break

    values = {
        "TELEGRAM_ENABLED": "true",
        "TELEGRAM_API_ID": api_id,
        "TELEGRAM_API_HASH": api_hash,
        "TELEGRAM_BOT_TOKEN": bot_token,
        "TELEGRAM_ALLOWED_USER_IDS": allowed_ids,
        "ADMIN_PASSWORD_HASH": hash_password(password),
        "SESSION_SECRET": secrets.token_urlsafe(48),
        "PUBLIC_ORIGIN": public_origin,
        "COOKIE_PATH": "/telegram/",
        "DATA_DIR": "/var/lib/telegram-media",
        "WEB_DIR": "/opt/telegram-media/web",
        "MAX_FILE_BYTES": "2147483648",
        "DISK_RESERVE_BYTES": "5368709120",
        "TRASH_RETENTION_DAYS": "30",
    }
    content = "".join(f"{key}={value}\n" for key, value in values.items())
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir="/etc", prefix="telegram-media.", delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o600)
    temporary_path.replace(ENV_PATH)
    subprocess.run(["systemctl", "restart", "telegram-media.service"], check=True)
    result = subprocess.run(["systemctl", "is-active", "telegram-media.service"], text=True, capture_output=True)
    if result.stdout.strip() != "active":
        raise SystemExit("配置已保存，但服务未正常启动。请运行 journalctl -u telegram-media.service 查看日志。")
    print("\n配置已安全保存，Telegram Media Vault 已启动。")


if __name__ == "__main__":
    main()
