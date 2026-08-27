from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


SERVICE_ID_HEADER = "X-NPD-Service-Id"
KEY_ID_HEADER = "X-NPD-Key-Id"
TIMESTAMP_HEADER = "X-NPD-Timestamp"
NONCE_HEADER = "X-NPD-Nonce"
CONTENT_HASH_HEADER = "X-NPD-Content-SHA256"
SIGNATURE_HEADER = "X-NPD-Signature"
CONTRACT_VERSION_HEADER = "X-NPD-Contract-Version"
EVENT_ID_HEADER = "X-NPD-Event-Id"


class ServiceAuthError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ReplayStore(Protocol):
    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> object: ...


@dataclass(frozen=True)
class ServiceIdentity:
    service_id: str
    roles: tuple[str, ...]
    keys: Mapping[str, bytes]


@dataclass(frozen=True)
class VerifiedService:
    service_id: str
    key_id: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class SigningKeyring:
    active_key_id: str
    keys: Mapping[str, bytes]

    @classmethod
    def from_file(cls, path: Path) -> "SigningKeyring":
        payload = _read_secret_document(path)
        signing = payload.get("webhook_signing")
        if not isinstance(signing, dict):
            raise ValueError("secret file is missing webhook_signing")
        active_key_id = str(signing.get("active_key_id") or "")
        keys = _decode_keys(signing.get("keys"))
        if not active_key_id or active_key_id not in keys:
            raise ValueError("webhook signing active_key_id is missing from keys")
        return cls(active_key_id=active_key_id, keys=keys)

    def sign(self, body: bytes, *, timestamp: int, event_id: str) -> dict[str, str]:
        content_hash = sha256_hex(body)
        canonical = webhook_canonical_message(
            timestamp=timestamp,
            event_id=event_id,
            content_hash=content_hash,
        )
        signature = hmac.new(
            self.keys[self.active_key_id], canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return {
            KEY_ID_HEADER: self.active_key_id,
            TIMESTAMP_HEADER: str(timestamp),
            CONTENT_HASH_HEADER: content_hash,
            SIGNATURE_HEADER: signature,
            CONTRACT_VERSION_HEADER: "agent-hub-bridge.v1",
            EVENT_ID_HEADER: event_id,
        }

    def verify(
        self,
        body: bytes,
        *,
        key_id: str,
        timestamp: int,
        event_id: str,
        signature: str,
    ) -> bool:
        key = self.keys.get(key_id)
        if key is None:
            return False
        canonical = webhook_canonical_message(
            timestamp=timestamp,
            event_id=event_id,
            content_hash=sha256_hex(body),
        )
        expected = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class ServiceAuthVerifier:
    def __init__(
        self,
        identities: Mapping[str, ServiceIdentity],
        replay_store: ReplayStore,
        *,
        max_clock_skew_seconds: int = 300,
        replay_ttl_seconds: int = 600,
        now: Callable[[], float] = time.time,
    ):
        self.identities = identities
        self.replay_store = replay_store
        self.max_clock_skew_seconds = max_clock_skew_seconds
        self.replay_ttl_seconds = replay_ttl_seconds
        self.now = now

    @classmethod
    def from_file(
        cls,
        path: Path,
        replay_store: ReplayStore,
        *,
        max_clock_skew_seconds: int = 300,
        replay_ttl_seconds: int = 600,
    ) -> "ServiceAuthVerifier":
        payload = _read_secret_document(path)
        raw_identities = payload.get("service_identities")
        if not isinstance(raw_identities, dict) or not raw_identities:
            raise ValueError("secret file is missing service_identities")
        identities: dict[str, ServiceIdentity] = {}
        for service_id, raw in raw_identities.items():
            if not isinstance(raw, dict):
                raise ValueError("service identity configuration must be an object")
            roles = tuple(str(role) for role in raw.get("roles", []))
            if "service" not in roles:
                raise ValueError("service identity must include the service role")
            identities[str(service_id)] = ServiceIdentity(
                service_id=str(service_id),
                roles=roles,
                keys=_decode_keys(raw.get("keys")),
            )
        return cls(
            identities,
            replay_store,
            max_clock_skew_seconds=max_clock_skew_seconds,
            replay_ttl_seconds=replay_ttl_seconds,
        )

    async def verify(
        self,
        *,
        method: str,
        path: str,
        query: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> VerifiedService:
        service_id = headers.get(SERVICE_ID_HEADER, "")
        key_id = headers.get(KEY_ID_HEADER, "")
        nonce = headers.get(NONCE_HEADER, "")
        signature = headers.get(SIGNATURE_HEADER, "")
        content_hash = headers.get(CONTENT_HASH_HEADER, "")
        timestamp_text = headers.get(TIMESTAMP_HEADER, "")
        if not all((service_id, key_id, nonce, signature, content_hash, timestamp_text)):
            raise ServiceAuthError("SERVICE_AUTH_REQUIRED", "Signed service authentication is required.")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", nonce):
            raise ServiceAuthError("SERVICE_AUTH_INVALID", "Service authentication is invalid.")
        identity = self.identities.get(service_id)
        key = identity.keys.get(key_id) if identity else None
        if identity is None or key is None:
            raise ServiceAuthError("SERVICE_AUTH_INVALID", "Service authentication is invalid.")
        try:
            timestamp = int(timestamp_text)
        except ValueError as exc:
            raise ServiceAuthError("SERVICE_AUTH_INVALID", "Service authentication is invalid.") from exc
        if abs(int(self.now()) - timestamp) > self.max_clock_skew_seconds:
            raise ServiceAuthError("SERVICE_AUTH_EXPIRED", "Service authentication timestamp is outside the allowed window.")
        calculated_hash = sha256_hex(body)
        if not hmac.compare_digest(calculated_hash, content_hash):
            raise ServiceAuthError("SERVICE_AUTH_INVALID", "Service authentication is invalid.")
        canonical = service_canonical_message(
            method=method,
            path=path,
            query=query,
            timestamp=timestamp,
            nonce=nonce,
            content_hash=content_hash,
        )
        expected = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ServiceAuthError("SERVICE_AUTH_INVALID", "Service authentication is invalid.")
        replay_key = f"npd:video-factory:v2:bridge:auth-replay:{service_id}:{key_id}:{nonce}"
        accepted = await self.replay_store.set(
            replay_key,
            "1",
            ex=self.replay_ttl_seconds,
            nx=True,
        )
        if not accepted:
            raise ServiceAuthError("SERVICE_AUTH_REPLAY", "This signed request has already been used.")
        return VerifiedService(service_id=service_id, key_id=key_id, roles=identity.roles)


def service_canonical_message(
    *, method: str, path: str, query: str, timestamp: int, nonce: str, content_hash: str
) -> str:
    return "\n".join((method.upper(), path, query, str(timestamp), nonce, content_hash))


def webhook_canonical_message(*, timestamp: int, event_id: str, content_hash: str) -> str:
    return "\n".join(("POST", "/agent-hub/events/v1", str(timestamp), event_id, content_hash))


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sign_service_request(
    *,
    key: bytes,
    service_id: str,
    key_id: str,
    method: str,
    path: str,
    query: str = "",
    body: bytes = b"",
    timestamp: int | None = None,
    nonce: str,
) -> dict[str, str]:
    issued_at = int(time.time()) if timestamp is None else timestamp
    content_hash = sha256_hex(body)
    canonical = service_canonical_message(
        method=method,
        path=path,
        query=query,
        timestamp=issued_at,
        nonce=nonce,
        content_hash=content_hash,
    )
    return {
        SERVICE_ID_HEADER: service_id,
        KEY_ID_HEADER: key_id,
        TIMESTAMP_HEADER: str(issued_at),
        NONCE_HEADER: nonce,
        CONTENT_HASH_HEADER: content_hash,
        SIGNATURE_HEADER: hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest(),
        CONTRACT_VERSION_HEADER: "agent-hub-bridge.v1",
    }


def _read_secret_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("service secret file does not exist")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("unsupported service secret file version")
    return payload


def _decode_keys(raw: Any) -> dict[str, bytes]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("key map must not be empty")
    decoded: dict[str, bytes] = {}
    for key_id, encoded in raw.items():
        try:
            secret = base64.b64decode(str(encoded), validate=True)
        except Exception as exc:
            raise ValueError("key material must be valid base64") from exc
        if len(secret) < 32:
            raise ValueError("HMAC key material must be at least 32 bytes")
        decoded[str(key_id)] = secret
    return decoded
