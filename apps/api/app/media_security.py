from __future__ import annotations

import asyncio
import hashlib
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field

from .models import StrictModel


class MediaSecurityError(RuntimeError):
    pass


class ArchiveContainerRejected(MediaSecurityError):
    pass


class MediaScanUnavailable(MediaSecurityError):
    pass


class UnsafeMediaRejected(MediaSecurityError):
    pass


class MediaScanResult(StrictModel):
    verdict: Literal["clean", "infected", "rejected", "error"]
    provider: str = Field(min_length=1, max_length=80)
    signature_version: str = Field(min_length=1, max_length=120)
    result_code: str = Field(min_length=1, max_length=120)
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    started_at: datetime
    completed_at: datetime


class MediaMalwareScanner(Protocol):
    async def scan(self, path: Path, *, expected_checksum_sha256: str) -> MediaScanResult: ...


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def reject_archive_container(path: Path) -> None:
    """Reject archive containers before a decoder can expand attacker-controlled data.

    V3-01-03 does not support archive ingestion, so the safest archive-bomb policy is no
    decompression at all. Media files with an archive signature never reach ffprobe or storage.
    """

    with path.open("rb") as handle:
        head = handle.read(512)
    archive = (
        head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
        or head.startswith(b"Rar!\x1a\x07")
        or head.startswith(b"7z\xbc\xaf\x27\x1c")
        or head.startswith(b"\x1f\x8b")
        or head.startswith(b"BZh")
        or head.startswith(b"\xfd7zXZ\x00")
        or (len(head) >= 262 and head[257:262] == b"ustar")
    )
    if archive:
        raise ArchiveContainerRejected("archive containers are not accepted by media ingestion")


def _scan_fixture(path: Path, expected_checksum_sha256: str) -> tuple[str, str]:
    digest = hashlib.sha256()
    eicar = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
    overlap = b""
    infected = False
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            haystack = overlap + chunk
            if eicar in haystack:
                infected = True
            overlap = haystack[-len(eicar) :]
    checksum = digest.hexdigest()
    if checksum != expected_checksum_sha256:
        raise MediaSecurityError("media changed between assembly and malware scan")
    return checksum, "EICAR_TEST_SIGNATURE" if infected else "CLEAN"


class DeterministicMediaMalwareScanner:
    """CI-safe scanner for the clean and EICAR rejection contracts only."""

    async def scan(self, path: Path, *, expected_checksum_sha256: str) -> MediaScanResult:
        started = utc_now()
        checksum, code = await asyncio.to_thread(_scan_fixture, path, expected_checksum_sha256)
        return MediaScanResult(
            verdict="infected" if code != "CLEAN" else "clean",
            provider="deterministic-eicar-contract",
            signature_version="fixture-v1",
            result_code=code,
            checksum_sha256=checksum,
            started_at=started,
            completed_at=utc_now(),
        )


class DisabledMediaMalwareScanner:
    async def scan(self, path: Path, *, expected_checksum_sha256: str) -> MediaScanResult:
        del path
        now = utc_now()
        return MediaScanResult(
            verdict="error",
            provider="disabled",
            signature_version="not-configured",
            result_code="MALWARE_SCANNER_NOT_CONFIGURED",
            checksum_sha256=expected_checksum_sha256,
            started_at=now,
            completed_at=now,
        )


class ClamdMediaMalwareScanner:
    """Bounded clamd INSTREAM client; it never submits media to an external provider."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout_seconds: float,
        max_stream_bytes: int,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.max_stream_bytes = max_stream_bytes
        self.chunk_size = chunk_size

    async def scan(self, path: Path, *, expected_checksum_sha256: str) -> MediaScanResult:
        started = utc_now()
        checksum = await asyncio.to_thread(_sha256_bounded, path, self.max_stream_bytes)
        if checksum != expected_checksum_sha256:
            raise MediaSecurityError("media changed between assembly and malware scan")

        async def exchange() -> str:
            reader, writer = await asyncio.open_connection(self.host, self.port)
            try:
                writer.write(b"zINSTREAM\x00")
                streamed = 0
                with path.open("rb") as handle:
                    while True:
                        chunk = await asyncio.to_thread(handle.read, self.chunk_size)
                        if not chunk:
                            break
                        streamed += len(chunk)
                        if streamed > self.max_stream_bytes:
                            raise MediaSecurityError("media exceeds malware scanner stream limit")
                        writer.write(struct.pack("!I", len(chunk)))
                        writer.write(chunk)
                        await writer.drain()
                writer.write(struct.pack("!I", 0))
                await writer.drain()
                response = await reader.readuntil(b"\x00")
                return response.rstrip(b"\x00").decode("utf-8", "replace")
            finally:
                writer.close()
                await writer.wait_closed()

        try:
            response = await asyncio.wait_for(exchange(), timeout=self.timeout_seconds)
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
            raise MediaScanUnavailable("malware scanner did not return a complete verdict") from exc
        if response.endswith(" OK"):
            verdict: Literal["clean", "infected", "rejected", "error"] = "clean"
            code = "CLEAN"
        elif response.endswith(" FOUND"):
            verdict = "infected"
            code = "MALWARE_FOUND"
        else:
            verdict = "error"
            code = "MALWARE_SCANNER_ERROR"
        return MediaScanResult(
            verdict=verdict,
            provider="clamd-instream",
            signature_version="clamd-runtime",
            result_code=code,
            checksum_sha256=checksum,
            started_at=started,
            completed_at=utc_now(),
        )


def _sha256_bounded(path: Path, maximum: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(chunk)
            if total > maximum:
                raise MediaSecurityError("media exceeds malware scanner stream limit")
            digest.update(chunk)
    return digest.hexdigest()


def create_media_malware_scanner(settings) -> MediaMalwareScanner:
    if settings.media_malware_scanner_mode == "fixture":
        return DeterministicMediaMalwareScanner()
    if settings.media_malware_scanner_mode == "clamd":
        return ClamdMediaMalwareScanner(
            settings.media_malware_scanner_host,
            settings.media_malware_scanner_port,
            timeout_seconds=settings.media_malware_scan_timeout_seconds,
            max_stream_bytes=settings.upload_max_size_bytes,
        )
    return DisabledMediaMalwareScanner()
