from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


_CREDENTIAL_REFERENCE_PATTERN = re.compile(
    r"(?i)\b(?:secret|vault|external)://"
    r"[a-z0-9][a-z0-9._-]{0,63}(?:/[a-z0-9][a-z0-9._-]{0,63}){1,7}\b"
)
_DIRECT_SECRET_PATTERNS = (
    re.compile(r"(?i)sk-(?:proj-)?[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)bearer\s+\S+"),
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?:\"?(?:api[_-]?key|token|password|secret)\"?\s*[:=]\s*\"?)"
    r"(?!//)[^\"\s,}]+"
)


class EvidenceSerializationError(ValueError):
    """A value cannot be represented by the canonical evidence contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EvidenceWriteReceipt:
    status: Literal["written", "fallback_written"]
    primary_path: Path
    evidence_path: Path
    sha256: str
    error_code: str | None
    secret_recorded: Literal[False] = False


def canonical_evidence_value(value: object) -> object:
    """Convert supported domain values into a deterministic JSON-safe tree."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Enum):
        return canonical_evidence_value(value.value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EvidenceSerializationError(
                "EVIDENCE_NON_FINITE_FLOAT",
                "evidence floats must be finite",
            )
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, (Path, UUID)):
        return str(value)
    if isinstance(value, BaseModel):
        return canonical_evidence_value(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: canonical_evidence_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceSerializationError(
                    "EVIDENCE_NON_STRING_KEY",
                    "evidence mappings require string keys",
                )
            result[key] = canonical_evidence_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [canonical_evidence_value(item) for item in value]
    raise EvidenceSerializationError(
        "EVIDENCE_UNSUPPORTED_TYPE",
        f"unsupported evidence type: {type(value).__name__}",
    )


def canonical_evidence_bytes(value: object) -> bytes:
    return json.dumps(
        canonical_evidence_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_evidence_sha256(value: object) -> str:
    return hashlib.sha256(canonical_evidence_bytes(value)).hexdigest()


def write_evidence_bundle(
    path: Path,
    payload: object,
    *,
    durable_fallback_context: Mapping[str, object],
    forbidden_values: tuple[str, ...] = (),
) -> EvidenceWriteReceipt:
    """Atomically persist evidence or a secret-free REVIEW_REQUIRED fallback."""

    primary_path = Path(path)
    try:
        serialized = canonical_evidence_bytes(payload) + b"\n"
        _require_secret_free(serialized, forbidden_values=forbidden_values)
        _atomic_write(primary_path, serialized)
        return EvidenceWriteReceipt(
            status="written",
            primary_path=primary_path,
            evidence_path=primary_path,
            sha256=hashlib.sha256(serialized).hexdigest(),
            error_code=None,
        )
    except Exception as exc:
        error_code = (
            exc.code
            if isinstance(exc, EvidenceSerializationError)
            else "EVIDENCE_SERIALIZATION_FAILED"
        )
        fallback_path = primary_path.with_name(
            f"{primary_path.stem}.serialization-error{primary_path.suffix or '.json'}"
        )
        fallback = {
            "evidence_version": 1,
            "verdict": "REVIEW_REQUIRED",
            "production_verdict": "NO-GO",
            "error": {
                "phase": "post_call_evidence_serialization",
                "code": error_code,
                "type": type(exc).__name__,
                "secret_recorded": False,
            },
            "durable_context": _safe_fallback_context(durable_fallback_context),
        }
        fallback_bytes = canonical_evidence_bytes(fallback) + b"\n"
        try:
            _require_secret_free(fallback_bytes, forbidden_values=forbidden_values)
        except EvidenceSerializationError:
            fallback["durable_context"] = {
                "status": "withheld",
                "reason": "fallback context failed secret containment",
            }
            fallback_bytes = canonical_evidence_bytes(fallback) + b"\n"
            _require_secret_free(fallback_bytes, forbidden_values=forbidden_values)
        _atomic_write(fallback_path, fallback_bytes)
        return EvidenceWriteReceipt(
            status="fallback_written",
            primary_path=primary_path,
            evidence_path=fallback_path,
            sha256=hashlib.sha256(fallback_bytes).hexdigest(),
            error_code=error_code,
        )


def _safe_fallback_context(value: Mapping[str, object]) -> object:
    try:
        return canonical_evidence_value(value)
    except Exception as exc:
        return {
            "status": "partially_unavailable",
            "serialization_error_type": type(exc).__name__,
        }


def _require_secret_free(payload: bytes, *, forbidden_values: tuple[str, ...]) -> None:
    text = payload.decode("utf-8")
    for forbidden in forbidden_values:
        if forbidden and forbidden in text:
            raise EvidenceSerializationError(
                "EVIDENCE_SECRET_DETECTED",
                "a forbidden value was found in evidence",
            )
    if any(pattern.search(text) for pattern in _DIRECT_SECRET_PATTERNS):
        raise EvidenceSerializationError(
            "EVIDENCE_SECRET_DETECTED",
            "a credential pattern was found in evidence",
        )
    reference_free = _CREDENTIAL_REFERENCE_PATTERN.sub(
        "//credential-reference",
        text,
    )
    if _SECRET_ASSIGNMENT_PATTERN.search(reference_free):
        raise EvidenceSerializationError(
            "EVIDENCE_SECRET_DETECTED",
            "a credential pattern was found in evidence",
        )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise
