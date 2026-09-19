from __future__ import annotations

import getpass
import secrets
import sys

from .security import hash_password


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] != "hash-password":
        raise SystemExit("Usage: python -m telegram_media.cli hash-password")
    first = getpass.getpass("New administrator password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match")
    print(f"ADMIN_PASSWORD_HASH={hash_password(first)}")
    print(f"SESSION_SECRET={secrets.token_urlsafe(48)}")


if __name__ == "__main__":
    main()
