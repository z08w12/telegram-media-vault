from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path


parser = argparse.ArgumentParser(description="Add Telegram Media Vault to an existing Nginx HTTPS server block")
parser.add_argument("--site", type=Path, required=True, help="Path to the enabled Nginx site configuration")
parser.add_argument("--server-name", required=True, help="Existing HTTPS server_name to update")
args = parser.parse_args()

target = args.site.resolve()
if not target.is_file():
    raise SystemExit(f"Nginx site configuration does not exist: {target}")
include_line = "    include /etc/nginx/snippets/telegram-media.conf;"
text = target.read_text(encoding="utf-8")
backup_directory = Path("/var/backups/telegram-media")
backup_directory.mkdir(parents=True, exist_ok=True)
backup = backup_directory / f"{target.name}.{int(time.time())}.conf"

if include_line not in text:
    marker = f"    server_name {args.server_name};"
    position = text.find(marker)
    if position < 0:
        raise SystemExit("Could not find the HTTPS server block marker")
    insertion = position + len(marker)
    updated = text[:insertion] + "\n\n" + include_line + text[insertion:]
    shutil.copy2(target, backup)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(target)

result = subprocess.run(["nginx", "-t"], text=True, capture_output=True)
if result.returncode != 0:
    if backup.exists():
        shutil.copy2(backup, target)
    sys.stderr.write(result.stdout + result.stderr)
    raise SystemExit("nginx validation failed; the previous configuration was restored")

subprocess.run(["systemctl", "reload", "nginx"], check=True)
print(f"Nginx configured; backup: {backup if backup.exists() else 'existing include reused'}")
