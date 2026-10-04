"""One fixed Cloud proxy/TLS path for Content POST and separately approved auth GET."""
from __future__ import annotations

import os
import ssl
import json
import subprocess
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Literal
from urllib.request import getproxies

import httpx
from httpx._utils import URLPattern, get_environment_proxies
from pydantic import Field, model_validator

from .models import StrictModel
from .codex_cloud_content_secret import (
    BACKEND_ID, CONTENT_ALIAS, CONTENT_PROVIDER, HTTPS_HOST, NETWORK_SECRET_VARIABLE,
    CodexCloudContentSecretTransport, uses_codex_cloud_content_proxy,
)
from .mvp1_provider_admission import Mvp1AdmissionScope, ProtectedResolverReference, canonical, digest

ORIGIN = "https://api.openai.com"
AUTH_PROBE_PATH = "/v1/models/gpt-6-luna"
RESPONSES_PATH = "/v1/responses"
CLIENT_ID = "codex-cloud-content-http-v1"

# Fixed public compatibility request. No caller text, tools or business data.
# A 16-token acknowledgement allocation and store=False keep this bounded and
# separate from stored business content. No Content profile/request is changed.
_CANARY_REQUEST_BYTES = canonical({"model": "gpt-6-luna", "reasoning": {"effort": "none"},
    "input": "Return exactly OK.", "max_output_tokens": 16, "store": False})
CANARY_REQUEST_SHA256 = digest(json.loads(_CANARY_REQUEST_BYTES))


def canary_request_payload():
    return json.loads(_CANARY_REQUEST_BYTES)  # Fresh copy, fixed trusted source.


def validate_canary_payload(payload):
    try:
        matches = type(payload) is dict and canonical(payload) == _CANARY_REQUEST_BYTES
    except Exception:
        matches = False
    if not matches:
        raise ContentHTTPPathError("CONTENT_CANARY_FIXED_PAYLOAD_REQUIRED")


def current_source_head():
    try:
        root = Path(__file__).resolve().parents[3]
        subprocess.check_call(["git", "diff", "--quiet", "HEAD", "--"], cwd=root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
            cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        raise ContentHTTPPathError("CONTENT_CANARY_SOURCE_HEAD_UNAVAILABLE") from None


class ContentHTTPMode(Enum):
    AUTH_PROBE = "AUTH_PROBE"
    RESPONSES_CANARY = "RESPONSES_CANARY"
    CONTENT_RESPONSES = "CONTENT_RESPONSES"


class ContentHTTPPathError(RuntimeError):
    """Only fixed public codes; never credential, proxy URL or underlying errors."""


def cloud_proxy_context():
    """Read HTTPX's actual environment route, retaining booleans only."""
    proxies = get_environment_proxies()
    environment = getproxies()
    official = httpx.URL(ORIGIN)
    bypass = ("*" in {item.strip() for item in environment.get("no", "").split(",")}
        or any(value is None and URLPattern(pattern).matches(official)
               for pattern, value in proxies.items()))
    https = bool(environment.get("https") or environment.get("all"))
    return {
        "HTTPS_PROXY_AVAILABLE": https,
        "HTTP_PROXY_AVAILABLE": bool(environment.get("http")),
        "NO_PROXY_EXCLUDES_API_OPENAI_COM": bypass,
        "CA_CONFIGURATION_AVAILABLE": bool(os.environ.get("SSL_CERT_FILE")
            or os.environ.get("SSL_CERT_DIR") or ssl.get_default_verify_paths().cafile),
        "API_OPENAI_COM_PROXY_ROUTE_ENABLED": https and not bypass,
    }


class ContentAuthProbeApproval(StrictModel):
    """Independent GET-only authority; cannot activate Content generation/budget."""
    model_config = {"frozen": True}
    schema_name: Literal["codex-cloud-content-auth-probe-v1"] = "codex-cloud-content-auth-probe-v1"
    owner_decision_id: str = Field(pattern=r"^VF-MVP1-[A-Z0-9-]{3,120}$")
    approved_by: Literal["Owner (GitHub: vangnguyen)"]
    auth_probe_authorized: bool = False
    source_head: str = Field(pattern=r"^[a-f0-9]{40}$")
    content_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_scope_raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    valid_from_utc: datetime
    expires_at_utc: datetime
    provider: Literal["openai-storyboard-content"] = CONTENT_PROVIDER
    backend_id: Literal["codex-cloud-network-secret-content-v1"] = BACKEND_ID
    credential_alias: Literal["secret://openai/video-factory-content-generation"] = CONTENT_ALIAS
    network_secret_variable: Literal["NPD_VF_CONTENT_API_KEY"] = NETWORK_SECRET_VARIABLE
    credential_host: Literal["api.openai.com"] = HTTPS_HOST
    method: Literal["GET"] = "GET"
    path: Literal["/v1/models/gpt-6-luna"] = AUTH_PROBE_PATH
    model: Literal["gpt-6-luna"] = "gpt-6-luna"
    max_attempts: Literal[1] = 1
    automatic_retry: Literal[False] = False
    content_execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded_window(self):
        if (self.valid_from_utc.tzinfo is None or self.expires_at_utc.tzinfo is None
                or self.valid_from_utc.utcoffset() != timedelta(0)
                or self.expires_at_utc.utcoffset() != timedelta(0)
                or not timedelta(0) < self.expires_at_utc-self.valid_from_utc <= timedelta(minutes=60)):
            raise ValueError("CONTENT_AUTH_PROBE_WINDOW_INVALID")
        return self

    def validate_binding(self, scope, raw_sha):
        validated = type(self).model_validate(self.model_dump())
        if (not validated.auth_probe_authorized
                or not validated.valid_from_utc <= datetime.now(timezone.utc) < validated.expires_at_utc
                or validated.content_scope_sha256 != digest(scope.model_dump(mode="json"))
                or validated.content_scope_raw_sha256 != raw_sha
                or validated.model != scope.model):
            raise ContentHTTPPathError("CONTENT_AUTH_PROBE_OWNER_AUTHORITY_REQUIRED")


class ContentResponsesCanaryApproval(StrictModel):
    """Independent POST-only authority, without Content execution or budget."""
    model_config = {"frozen": True}
    schema_name: Literal["codex-cloud-content-responses-canary-v1"] = "codex-cloud-content-responses-canary-v1"
    owner_decision_id: str = Field(pattern=r"^VF-MVP1-[A-Z0-9-]{3,120}$")
    approved_by: Literal["Owner (GitHub: vangnguyen)"]
    responses_canary_authorized: bool = False
    source_head: str = Field(pattern=r"^[a-f0-9]{40}$")
    content_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_scope_raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    valid_from_utc: datetime
    expires_at_utc: datetime
    provider: Literal["openai-storyboard-content"] = CONTENT_PROVIDER
    backend_id: Literal["codex-cloud-network-secret-content-v1"] = BACKEND_ID
    credential_alias: Literal["secret://openai/video-factory-content-generation"] = CONTENT_ALIAS
    network_secret_variable: Literal["NPD_VF_CONTENT_API_KEY"] = NETWORK_SECRET_VARIABLE
    credential_host: Literal["api.openai.com"] = HTTPS_HOST
    method: Literal["POST"] = "POST"
    path: Literal["/v1/responses"] = RESPONSES_PATH
    model: Literal["gpt-6-luna"] = "gpt-6-luna"
    canary_request_sha256: Literal[CANARY_REQUEST_SHA256] = CANARY_REQUEST_SHA256
    max_attempts: Literal[1] = 1
    automatic_retry: Literal[False] = False
    content_execution_authorized: Literal[False] = False
    content_budget_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded_window(self):
        if (self.valid_from_utc.tzinfo is None or self.expires_at_utc.tzinfo is None
                or self.valid_from_utc.utcoffset() != timedelta(0)
                or self.expires_at_utc.utcoffset() != timedelta(0)
                or not timedelta(0) < self.expires_at_utc-self.valid_from_utc <= timedelta(minutes=60)):
            raise ValueError("CONTENT_CANARY_WINDOW_INVALID")
        return self

    def validate_binding(self, scope, raw_sha):
        # Revalidation also rejects model_copy/model_construct authority bypasses.
        validated = type(self).model_validate(self.model_dump())
        disabled = Mvp1AdmissionScope.model_validate(scope.model_dump())
        if (not validated.responses_canary_authorized or disabled.execution_authorized
                or validated.source_head != current_source_head()
                or not validated.valid_from_utc <= datetime.now(timezone.utc) < validated.expires_at_utc
                or validated.content_scope_sha256 != digest(disabled.model_dump(mode="json"))
                or validated.content_scope_raw_sha256 != raw_sha
                or (disabled.capability, disabled.provider_key, disabled.credential_alias, disabled.model)
                    != ("content_generation", CONTENT_PROVIDER, CONTENT_ALIAS, validated.model)):
            raise ContentHTTPPathError("CONTENT_CANARY_OWNER_AUTHORITY_REQUIRED")


class CodexCloudContentHTTPClient:
    """No selectable origin/alias/proxy or custom transport; no credential at construction."""
    client_id = CLIENT_ID

    def __init__(self, resolver, *, timeout_seconds, transport=None):
        if transport is not None:
            raise ContentHTTPPathError("CUSTOM_TRANSPORT_PROXY_BYPASS_RISK")
        self._check_binding(resolver)
        if isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 90:
            raise ContentHTTPPathError("CONTENT_CLOUD_TIMEOUT_INVALID")
        self._resolver, self._timeout = resolver, timeout_seconds

    @staticmethod
    def _check_binding(resolver):
        if (type(resolver) is not ProtectedResolverReference
                or not uses_codex_cloud_content_proxy(resolver)
                or type(resolver.transport) is not CodexCloudContentSecretTransport):
            raise ContentHTTPPathError("CONTENT_CLOUD_PROTECTED_BACKEND_REQUIRED")
        backend = resolver.transport
        if (backend.backend_id, backend.logical_alias, backend.network_secret_variable,
                backend.provider_key, backend.https_host) != (
                BACKEND_ID, CONTENT_ALIAS, NETWORK_SECRET_VARIABLE, CONTENT_PROVIDER, HTTPS_HOST):
            raise ContentHTTPPathError("CONTENT_CLOUD_FIXED_BINDING_REQUIRED")

    def __repr__(self):
        return f"<{type(self).__name__} {CLIENT_ID}>"

    async def _send(self, *, mode, context=None, approval=None, payload=None):
        if type(mode) is not ContentHTTPMode:
            raise ContentHTTPPathError("CONTENT_HTTP_MODE_REQUIRED")
        if mode is ContentHTTPMode.RESPONSES_CANARY:
            if type(approval) is not ContentResponsesCanaryApproval:
                raise ContentHTTPPathError("CONTENT_CANARY_OWNER_AUTHORITY_REQUIRED")
            validate_canary_payload(payload)
            # Never retain caller-owned mutable text across the async client entry.
            payload = canary_request_payload()
            approval.validate_binding(self._resolver.scope, self._resolver.raw_file_sha256)
        self._check_binding(self._resolver)
        if not cloud_proxy_context()["API_OPENAI_COM_PROXY_ROUTE_ENABLED"]:
            raise ContentHTTPPathError("PLACEHOLDER_ESCAPED_PROXY_CONTEXT")
        try:
            if mode is ContentHTTPMode.AUTH_PROBE:
                credential = self._resolver.resolve_for_auth_probe(approval)
            elif mode is ContentHTTPMode.RESPONSES_CANARY:
                credential = self._resolver.resolve_for_responses_canary(approval)
            else:
                credential = self._resolver.resolve_for_context(context)
        except Exception:
            raise ContentHTTPPathError("CONTENT_CREDENTIAL_UNAVAILABLE") from None
        if not isinstance(credential, str) or not credential:
            raise ContentHTTPPathError("CONTENT_CREDENTIAL_UNAVAILABLE")
        # All three modes share this constructor, TLS/CA route and Bearer construction.
        async with httpx.AsyncClient(base_url=ORIGIN, timeout=self._timeout,
                follow_redirects=False, trust_env=True, verify=True) as client:
            headers = {"Authorization": f"Bearer {credential}"}
            if mode is ContentHTTPMode.AUTH_PROBE:
                return await client.get(AUTH_PROBE_PATH, headers=headers)
            return await client.post(RESPONSES_PATH, headers=headers, json=payload)

    async def responses(self, payload, *, context):
        return await self._send(mode=ContentHTTPMode.CONTENT_RESPONSES, context=context, payload=payload)

    async def auth_probe(self, approval):
        if type(approval) is not ContentAuthProbeApproval:
            raise ContentHTTPPathError("CONTENT_AUTH_PROBE_OWNER_AUTHORITY_REQUIRED")
        approval.validate_binding(self._resolver.scope, self._resolver.raw_file_sha256)
        return await self._send(mode=ContentHTTPMode.AUTH_PROBE, approval=approval)

    async def responses_canary(self, payload, approval):
        return await self._send(mode=ContentHTTPMode.RESPONSES_CANARY, approval=approval, payload=payload)
