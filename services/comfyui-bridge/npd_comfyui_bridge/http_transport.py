"""Bounded official ComfyUI wire contracts, inert until explicitly configured.

Only trusted bridge code calls this client. A UUID is an identity, not remote
deduplication: the caller MUST durably reserve dispatch before submit_prompt.
No method retries a write, clears queues or globally interrupts a GPU.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import re
from urllib.parse import urlsplit
import uuid

import httpx

JSON_LIMIT = 2 * 1024 * 1024
IMAGE_LIMIT = 32 * 1024 * 1024
MEDIA_LIMIT = 250 * 1024 * 1024


class ComfyTransportError(RuntimeError):
    def __init__(self, code, *, uncertain_dispatch=False, retry_after_seconds=None):
        super().__init__(code)
        self.code = code
        self.uncertain_dispatch = uncertain_dispatch
        self.retry_after_seconds = retry_after_seconds


def canonical_job_id(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise ComfyTransportError('COMFY_JOB_ID_INVALID') from None
    return value


def retry_after(value):
    if not value:
        return None
    if value.isdigit():
        return min(86400, int(value))
    try:
        deadline = parsedate_to_datetime(value)
        if deadline.tzinfo is None:
            return None
        return min(86400, max(0, int((deadline - datetime.now(timezone.utc)).total_seconds())))
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class RemoteArtifact:
    """A descriptor selected from a permitted output node's saved history."""
    filename: str
    subfolder: str = ''
    type: str = 'output'

    def __post_init__(self):
        if (not isinstance(self.filename, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}', self.filename)
                or '..' in self.filename or self.type != 'output'
                or not isinstance(self.subfolder, str) or len(self.subfolder) > 240
                or self.subfolder and not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', self.subfolder)):
            raise ComfyTransportError('COMFY_ARTIFACT_DESCRIPTOR_INVALID')


class _CredentialTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner, token):
        self.inner, self.token = inner, token

    async def handle_async_request(self, request):
        headers = httpx.Headers(request.headers)
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        forwarded = httpx.Request(request.method, request.url, headers=headers,
                                 stream=request.stream, extensions=request.extensions)
        return await self.inner.handle_async_request(forwarded)

    async def aclose(self):
        await self.inner.aclose()


class ComfyHTTPTransport:
    """Operator-selected origin and targeted-cancel API profile only.

    server_source_sha256 is an operator contract pin, not an automatic claim
    about the remote installation. Live acceptance must verify that pin.
    """
    def __init__(self, *, origin, server_source_sha256, enabled=False, bearer_token='',
                 allowed_http_hosts=(), transport=None, timeout_seconds=20):
        if (not isinstance(allowed_http_hosts, (tuple, list)) or len(allowed_http_hosts) > 10
                or any(not isinstance(h, str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,199}', h) for h in allowed_http_hosts)):
            raise ValueError('COMFY_HTTP_HOSTS_INVALID')
        try:
            parts = urlsplit(origin)
            port = parts.port
        except (ValueError, TypeError):
            raise ValueError('COMFY_ORIGIN_INVALID') from None
        if (not isinstance(origin, str) or len(origin) > 2000 or not parts.hostname
                or parts.scheme not in {'https', 'http'} or parts.username or parts.password
                or parts.path not in {'', '/'} or parts.query or parts.fragment
                or '\\' in origin or '%' in origin or any(ord(c) < 33 for c in origin)
                or port is not None and not 1 <= port <= 65535
                or parts.scheme == 'http' and parts.hostname not in {'127.0.0.1', 'localhost', '::1', *allowed_http_hosts}):
            raise ValueError('COMFY_ORIGIN_INVALID')
        if not isinstance(server_source_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', server_source_sha256):
            raise ValueError('COMFY_SERVER_PROFILE_PIN_REQUIRED')
        if (not isinstance(bearer_token, str) or len(bearer_token) > 8192
                or any(c.isspace() or ord(c) < 33 for c in bearer_token)
                or not 1 <= timeout_seconds <= 60):
            raise ValueError('COMFY_TRANSPORT_CONFIG_INVALID')
        self.origin = origin.rstrip('/')
        self.server_source_sha256 = server_source_sha256
        self.configured = bool(enabled)
        self.fixture = isinstance(transport, (httpx.MockTransport, httpx.ASGITransport))
        self.timeout_seconds = timeout_seconds
        self._token, self._transport, self._client = bearer_token, transport, None

    def _http(self):
        if not self.configured:
            raise ComfyTransportError('COMFY_HTTP_NOT_CONFIGURED')
        if self._client is None:
            inner = self._transport or httpx.AsyncHTTPTransport(retries=0, trust_env=False)
            self._client = httpx.AsyncClient(transport=_CredentialTransport(inner, self._token),
                timeout=self.timeout_seconds, follow_redirects=False, trust_env=False)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _read(self, method, path, *, limit=JSON_LIMIT, params=None, json_body=None,
                    files=None, data=None, dispatch=False, missing_ok=False):
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with self._http().stream(method, self.origin + path, params=params,
                        json=json_body, files=files, data=data) as response:
                    if response.status_code == 404 and missing_ok:
                        return None, ''
                    if response.status_code != 200:
                        # A gateway/5xx/redirect can follow an accepted write.
                        uncertain = dispatch and response.status_code not in {400, 401, 403, 404, 413, 422, 429}
                        raise ComfyTransportError('COMFY_RATE_LIMITED' if response.status_code == 429 else 'COMFY_HTTP_FAILED',
                            uncertain_dispatch=uncertain, retry_after_seconds=retry_after(response.headers.get('Retry-After')))
                    declared = response.headers.get('Content-Length')
                    if declared and (not declared.isdigit() or int(declared) > limit):
                        raise ComfyTransportError('COMFY_RESPONSE_TOO_LARGE', uncertain_dispatch=dispatch)
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > limit:
                            raise ComfyTransportError('COMFY_RESPONSE_TOO_LARGE', uncertain_dispatch=dispatch)
                        chunks.append(chunk)
                    return b''.join(chunks), response.headers.get('Content-Type', '').split(';')[0].lower()
        except (httpx.HTTPError, TimeoutError):
            raise ComfyTransportError('COMFY_NETWORK_FAILED', uncertain_dispatch=dispatch) from None

    async def _json(self, method, path, **kwargs):
        raw, mime = await self._read(method, path, **kwargs)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            if not isinstance(value, dict) or mime != 'application/json':
                raise ValueError()
            return value
        except (ValueError, UnicodeError):
            raise ComfyTransportError('COMFY_JSON_INVALID', uncertain_dispatch=kwargs.get('dispatch', False)) from None

    async def submit_prompt(self, *, prompt_id, graph):
        canonical_job_id(prompt_id)
        try:
            raw = json.dumps(graph, allow_nan=False).encode()
        except (TypeError, ValueError):
            raise ComfyTransportError('COMFY_GRAPH_INVALID') from None
        if not isinstance(graph, dict) or not graph or len(raw) > JSON_LIMIT:
            raise ComfyTransportError('COMFY_GRAPH_INVALID')
        value = await self._json('POST', '/prompt', json_body={'prompt_id': prompt_id, 'prompt': graph}, dispatch=True)
        if value.get('prompt_id') != prompt_id or value.get('error') or not isinstance(value.get('node_errors'), dict):
            raise ComfyTransportError('COMFY_SUBMIT_BINDING_INVALID', uncertain_dispatch=True)
        return prompt_id

    async def get_job(self, prompt_id):
        canonical_job_id(prompt_id)
        value = await self._json('GET', '/api/jobs/' + prompt_id, missing_ok=True)
        if value is not None and (value.get('id') != prompt_id or value.get('status') not in {'pending', 'in_progress', 'completed', 'failed', 'cancelled'}):
            raise ComfyTransportError('COMFY_JOB_BINDING_INVALID')
        return value

    async def history(self, prompt_id):
        canonical_job_id(prompt_id)
        value = await self._json('GET', '/history/' + prompt_id)
        if value and (set(value) != {prompt_id} or not isinstance(value.get(prompt_id), dict)):
            raise ComfyTransportError('COMFY_HISTORY_BINDING_INVALID')
        return value.get(prompt_id) if value else None

    async def cancel_job(self, prompt_id):
        canonical_job_id(prompt_id)
        value = await self._json('POST', '/api/jobs/' + prompt_id + '/cancel', json_body={})
        if set(value) != {'cancelled'} or type(value['cancelled']) is not bool:
            raise ComfyTransportError('COMFY_CANCEL_RESPONSE_INVALID')
        return value['cancelled']

    async def upload_image(self, *, filename, content, expected_sha256, mime_type):
        if (not isinstance(content, bytes) or not 1 <= len(content) <= IMAGE_LIMIT
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,120}\.(png|jpg|jpeg)', filename or '')
                or mime_type not in {'image/png', 'image/jpeg'}
                or hashlib.sha256(content).hexdigest() != expected_sha256):
            raise ComfyTransportError('COMFY_UPLOAD_INVALID')
        # Full image decoding/rights/scope belongs to the trusted staging caller.
        raw, mime = await self._read('POST', '/upload/image', files={'image': (filename, content, mime_type)},
                                    data={'type': 'input', 'overwrite': 'false'})
        try:
            value = json.loads(raw)
            if mime != 'application/json' or value.get('name') != filename or value.get('subfolder') != '' or value.get('type') != 'input':
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ComfyTransportError('COMFY_UPLOAD_BINDING_INVALID') from None
        # Verify the server stored the exact bytes; never overwrite its files.
        readback, returned_mime = await self._read('GET', '/view', params={'filename': filename, 'subfolder': '', 'type': 'input'}, limit=IMAGE_LIMIT)
        if hashlib.sha256(readback).hexdigest() != expected_sha256 or returned_mime not in {mime_type, 'application/octet-stream'}:
            raise ComfyTransportError('COMFY_UPLOAD_CHECKSUM_INVALID')
        return filename

    async def download_artifact(self, artifact: RemoteArtifact):
        if not isinstance(artifact, RemoteArtifact):
            raise ComfyTransportError('COMFY_ARTIFACT_DESCRIPTOR_INVALID')
        extension = artifact.filename.rsplit('.', 1)[-1].lower()
        expected = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'mp4': 'video/mp4'}.get(extension)
        if expected is None:
            raise ComfyTransportError('COMFY_ARTIFACT_TYPE_UNSUPPORTED')
        raw, mime = await self._read('GET', '/view', params={'filename': artifact.filename,
            'subfolder': artifact.subfolder, 'type': artifact.type}, limit=IMAGE_LIMIT if extension != 'mp4' else MEDIA_LIMIT)
        magic = (raw.startswith(b'\x89PNG\r\n\x1a\n') if extension == 'png' else
                 raw.startswith(b'\xff\xd8\xff') if extension in {'jpg', 'jpeg'} else len(raw) >= 12 and raw[4:8] == b'ftyp')
        if not magic or mime not in {expected, 'application/octet-stream'}:
            raise ComfyTransportError('COMFY_ARTIFACT_CONTENT_INVALID')
        # Magic is not a decode result; caller must fully validate/register.
        return raw, expected
