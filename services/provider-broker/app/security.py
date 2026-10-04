"""Pure stdlib secret custody and internal authentication; no logging or hashing."""
from __future__ import annotations

import hmac
import os
import stat
from pathlib import Path


class SecurityError(RuntimeError):
    pass


def probe_file(path: Path):
    try:
        info = path.lstat()
    except OSError:
        return {"exists": False, "non_empty": False, "permissions_valid": False}
    return {"exists": True, "non_empty": info.st_size > 0,
        "permissions_valid": stat.S_ISREG(info.st_mode) and info.st_uid == 0
            and info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o600}


def read_secret(path: Path):
    flags = probe_file(path)
    if not flags["exists"] or not flags["non_empty"]:
        raise SecurityError("BROKER_SECRET_NOT_INSTALLED")
    if not flags["permissions_valid"]:
        raise SecurityError("BROKER_SECRET_PERMISSIONS_INVALID")
    fd = None
    try:
        before = path.lstat()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        opened = os.fstat(fd)
        if ((before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or not stat.S_ISREG(opened.st_mode) or opened.st_uid != 0 or opened.st_gid != 0
            or stat.S_IMODE(opened.st_mode) != 0o600 or not 0 < opened.st_size <= 16384):
            raise SecurityError("BROKER_SECRET_PERMISSIONS_INVALID")
        value = os.read(fd, 16385).decode("utf-8").rstrip("\r\n")
        if not value:
            raise SecurityError("BROKER_SECRET_NOT_INSTALLED")
        return value
    except (OSError, UnicodeError):
        raise SecurityError("BROKER_SECRET_NOT_INSTALLED") from None
    finally:
        if fd is not None:
            os.close(fd)


def authenticate(headers, token_file: Path):
    values = headers.getlist("authorization")
    if len(values) != 1 or len(values[0]) > 2048 or not values[0].startswith("Bearer "):
        raise SecurityError("BROKER_UNAUTHORIZED")
    supplied = values[0][7:]
    try:
        expected = read_secret(token_file)
        # Bytes allow arbitrary UTF-8 without leaking a compare_digest exception.
        matches = hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
    except SecurityError:
        raise SecurityError("BROKER_UNAUTHORIZED") from None
    if not matches:
        raise SecurityError("BROKER_UNAUTHORIZED")
