from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .auto_edit_models import MediaKind


class MediaValidationError(ValueError):
    pass


_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_MIME_KIND: dict[str, MediaKind] = {
    "video/mp4": "video",
    "video/quicktime": "video",
    "video/webm": "video",
    "audio/mpeg": "audio",
    "audio/wav": "audio",
    "audio/x-wav": "audio",
    "audio/flac": "audio",
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "text/vtt": "subtitle",
    "application/x-subrip": "subtitle",
    "text/plain": "subtitle",
}


def safe_upload_filename(original: str) -> str:
    leaf = original.replace("\\", "/").rsplit("/", 1)[-1].strip()
    ascii_name = unicodedata.normalize("NFKD", leaf).encode("ascii", "ignore").decode("ascii")
    sanitized = _SAFE_FILENAME.sub("-", ascii_name).strip(".-_")
    if not sanitized:
        sanitized = "upload.bin"
    if len(sanitized) > 128:
        suffix = Path(sanitized).suffix[:16]
        stem_limit = max(1, 128 - len(suffix))
        sanitized = f"{Path(sanitized).stem[:stem_limit]}{suffix}"
    return sanitized


def sniff_media(path: Path, declared_content_type: str) -> tuple[MediaKind, str]:
    with path.open("rb") as handle:
        head = handle.read(4096)
    detected: str | None = None
    if len(head) >= 12 and head[4:8] == b"ftyp":
        detected = "video/quicktime" if head[8:12] == b"qt  " else "video/mp4"
    elif head.startswith(b"\x1aE\xdf\xa3"):
        detected = "video/webm"
    elif head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        detected = "audio/wav"
    elif head.startswith(b"fLaC"):
        detected = "audio/flac"
    elif head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        detected = "audio/mpeg"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif head.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        detected = "image/webp"
    else:
        try:
            text = head.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = ""
        if text.startswith("WEBVTT"):
            detected = "text/vtt"
        elif "-->" in text:
            detected = "application/x-subrip"

    if detected is None:
        raise MediaValidationError("unsupported or unrecognized media signature")
    declared = declared_content_type.split(";", 1)[0].strip().lower()
    if declared not in _MIME_KIND:
        raise MediaValidationError("declared content type is not allowed")
    detected_kind = _MIME_KIND[detected]
    declared_kind = _MIME_KIND[declared]
    if detected_kind != declared_kind:
        raise MediaValidationError("declared content type does not match media signature")
    return detected_kind, detected
