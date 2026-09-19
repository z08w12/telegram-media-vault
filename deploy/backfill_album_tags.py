from __future__ import annotations

import argparse
from pathlib import Path

from telegram_media.bot import extract_hashtags
from telegram_media.database import Database


def backfill(database_path: Path) -> tuple[int, int]:
    db = Database(database_path)
    try:
        with db.lock:
            groups = db.connection.execute(
                """SELECT DISTINCT telegram_chat_id,grouped_id FROM media
                   WHERE grouped_id IS NOT NULL AND caption IS NOT NULL AND caption<>''"""
            ).fetchall()
        tagged_groups = 0
        for group in groups:
            chat_id = int(group["telegram_chat_id"])
            grouped_id = str(group["grouped_id"])
            names = [
                tag
                for caption in db.group_captions(chat_id, grouped_id)
                for tag in extract_hashtags(caption)
            ]
            if names:
                db.add_tag_names(
                    0,
                    names,
                    telegram_chat_id=chat_id,
                    grouped_id=grouped_id,
                )
                tagged_groups += 1
        return len(groups), tagged_groups
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill caption hashtags across Telegram media groups")
    parser.add_argument("database", type=Path, help="Path to media.db")
    args = parser.parse_args()
    scanned, tagged = backfill(args.database)
    print(f"Scanned {scanned} media groups; synchronized tags for {tagged} groups.")


if __name__ == "__main__":
    main()
