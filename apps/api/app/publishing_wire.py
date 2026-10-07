"""Bounded official HTTP primitives. No application factory activates live calls."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import logging
import re
from types import MappingProxyType
from urllib.parse import parse_qsl, unquote, urlsplit

import httpx


MAX_BODY = 16 * 1024 * 1024
MAX_RESPONSE = 1024 * 1024
TIKTOK_UPLOAD_HOSTS = frozenset({'open-upload.tiktokapis.com', 'upload.us.tiktokapis.com'})
HOSTS = {'youtube': frozenset({'www.googleapis.com'}),
    'tiktok': frozenset({'open.tiktokapis.com', *TIKTOK_UPLOAD_HOSTS}),
    'instagram_reels': frozenset({'graph.facebook.com'}),
    'facebook': frozenset({'graph.facebook.com', 'rupload.facebook.com'})}
_sensitive = ContextVar('vf_publishing_wire_sensitive', default=False)


class PublishingWireError(RuntimeError):
    def __init__(self, code, *, status=None, uncertain=False, retry_after=None):
        self.code, self.status, self.uncertain, self.retry_after = code, status, uncertain, retry_after
        super().__init__(code)


class _PrivacyFilter(logging.Filter):
    def filter(self, _record):
        return not _sensitive.get()


def _install_privacy_filters():
    # Context-local: unrelated requests retain their configured logging behavior.
    names = {'httpx', 'httpcore', 'httpcore.connection', 'httpcore.connection_pool',
        'httpcore.http11', 'httpcore.http2', 'httpcore.proxy', 'httpcore.socks'}
    names.update(name for name in logging.Logger.manager.loggerDict if name.startswith(('httpx.', 'httpcore.')))
    for name in names:
        logger = logging.getLogger(name)
        if not any(isinstance(value, _PrivacyFilter) for value in logger.filters):
            logger.addFilter(_PrivacyFilter())


def official_url(value, platform):
    try:
        if not isinstance(value, str) or not value.isascii() or not 1 <= len(value) <= 4096 or any(ord(c) < 33 for c in value):
            raise ValueError()
        parsed = urlsplit(value)
        decoded = unquote(parsed.path)
        if any(key.lower() in {'access_token', 'authorization', 'api_key', 'key'} for key, _value in parse_qsl(parsed.query)):
            raise ValueError()
        if (platform not in HOSTS or parsed.scheme != 'https' or parsed.hostname not in HOSTS[platform]
            or parsed.username is not None or parsed.password is not None or parsed.fragment
            or parsed.port not in (None, 443) or '\\' in value or any(p in ('.', '..') for p in decoded.split('/'))
            or any(ord(c) < 32 for c in decoded)):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise PublishingWireError('PUBLISHING_OFFICIAL_ORIGIN_REQUIRED') from None


def bearer_headers(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{16,4096}', token):
        raise PublishingWireError('PUBLISHING_CREDENTIAL_INVALID')
    return {'Authorization': 'Bearer ' + token}


@dataclass(frozen=True)
class OfficialRequest:
    method: str
    url: str = field(repr=False)
    headers: dict = field(default_factory=dict, repr=False)
    body: bytes = field(default=b'', repr=False)

    def __post_init__(self):
        if self.method not in {'GET', 'POST', 'PUT', 'DELETE'} or not isinstance(self.body, bytes) or len(self.body) > MAX_BODY:
            raise PublishingWireError('PUBLISHING_REQUEST_INVALID')
        if not isinstance(self.headers, dict) or len(self.headers) > 12:
            raise PublishingWireError('PUBLISHING_REQUEST_INVALID')
        allowed = {'authorization', 'content-type', 'content-length', 'content-range',
            'x-upload-content-length', 'x-upload-content-type', 'offset', 'file_size', 'file_url'}
        for key, value in self.headers.items():
            if not isinstance(key, str) or key.lower() not in allowed or not isinstance(value, str) or len(value) > 8192 or not value.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise PublishingWireError('PUBLISHING_REQUEST_INVALID')
        if len({key.lower() for key in self.headers}) != len(self.headers):
            raise PublishingWireError('PUBLISHING_REQUEST_INVALID')
        length = next((value for key, value in self.headers.items() if key.lower() == 'content-length'), None)
        if length is not None and length != str(len(self.body)):
            raise PublishingWireError('PUBLISHING_REQUEST_LENGTH_MISMATCH')
        object.__setattr__(self, 'headers', MappingProxyType(dict(self.headers)))


@dataclass(frozen=True)
class OfficialResponse:
    status: int
    headers: dict = field(repr=False)
    body: bytes = field(repr=False)

    def json_object(self):
        try:
            value = json.loads(self.body)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, TypeError, RecursionError):
            raise PublishingWireError('PUBLISHING_PROVIDER_RESPONSE_INVALID', status=self.status) from None


class OfficialHTTPClient:
    """Official origins only, no redirects/retries/proxy env/cookies/SDK URL logs.

    Default mode cannot allocate a network transport. MockTransport is the sole
    test injection. Live activation/credential/approval/durable dispatch belongs
    to the application adapter, which is still deliberately disconnected.
    """
    def __init__(self, platform, *, network_enabled=False, transport=None):
        if platform not in HOSTS or type(network_enabled) is not bool or (transport is not None and not isinstance(transport, httpx.MockTransport)):
            raise PublishingWireError('PUBLISHING_TRANSPORT_CONFIGURATION_INVALID')
        self.platform, self.network_enabled, self.transport = platform, network_enabled, transport

    async def request(self, request):
        if not isinstance(request, OfficialRequest):
            raise PublishingWireError('PUBLISHING_REQUEST_INVALID')
        url = official_url(request.url, self.platform)
        if self.transport is None and not self.network_enabled:
            raise PublishingWireError('EXTERNAL_PUBLISHING_NOT_ACTIVATED')
        if urlsplit(url).hostname in TIKTOK_UPLOAD_HOSTS and any(key.lower() == 'authorization' for key in request.headers):
            raise PublishingWireError('PUBLISHING_UPLOAD_BEARER_FORBIDDEN')
        _install_privacy_filters(); privacy = _sensitive.set(True)
        transport = self.transport
        response = None
        owned = transport is None
        try:
            if owned:
                transport = httpx.AsyncHTTPTransport(verify=True, retries=0, trust_env=False, http2=False,
                    limits=httpx.Limits(max_connections=4, max_keepalive_connections=0))
            outgoing = httpx.Request(request.method, url, headers=dict(request.headers), content=request.body,
                extensions={'timeout': {'connect': 5.0, 'read': 30.0, 'write': 30.0, 'pool': 5.0}})
            response = await transport.handle_async_request(outgoing)
            if 300 <= response.status_code < 400 and not (self.platform == 'youtube' and request.method == 'PUT' and response.status_code == 308):
                raise PublishingWireError('PUBLISHING_REDIRECT_REJECTED', status=response.status_code, uncertain=request.method in {'POST', 'PUT', 'DELETE'})
            if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                raise PublishingWireError('PUBLISHING_COMPRESSED_RESPONSE_REJECTED', uncertain=request.method in {'POST', 'PUT', 'DELETE'})
            length = response.headers.get('content-length')
            if length is not None and (not re.fullmatch(r'[0-9]{1,10}', length) or int(length) > MAX_RESPONSE):
                raise PublishingWireError('PUBLISHING_RESPONSE_SIZE_LIMIT', status=response.status_code, uncertain=request.method in {'POST', 'PUT', 'DELETE'})
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw) + len(chunk) > MAX_RESPONSE:
                    raise PublishingWireError('PUBLISHING_RESPONSE_SIZE_LIMIT', status=response.status_code, uncertain=request.method in {'POST', 'PUT', 'DELETE'})
                raw.extend(chunk)
            headers = {name: value for name, value in response.headers.items() if name in {'location', 'range', 'content-range', 'retry-after'}}
            if any(len(value) > 4096 for value in headers.values()):
                raise PublishingWireError('PUBLISHING_RESPONSE_HEADER_LIMIT', uncertain=request.method in {'POST', 'PUT', 'DELETE'})
            return OfficialResponse(response.status_code, headers, bytes(raw))
        except PublishingWireError:
            raise
        except httpx.HTTPError:
            raise PublishingWireError('PUBLISHING_NETWORK_OUTCOME_UNKNOWN', uncertain=request.method in {'POST', 'PUT', 'DELETE'}) from None
        except Exception:
            raise PublishingWireError('PUBLISHING_TRANSPORT_FAILED', uncertain=request.method in {'POST', 'PUT', 'DELETE'}) from None
        finally:
            close_failed = False
            try:
                if response is not None:
                    try:
                        await response.aclose()
                    except Exception:
                        close_failed = True
                if owned and transport is not None:
                    try:
                        await transport.aclose()
                    except Exception:
                        close_failed = True
            finally:
                _sensitive.reset(privacy)
            if close_failed:
                raise PublishingWireError('PUBLISHING_TRANSPORT_CLOSE_FAILED', uncertain=request.method in {'POST', 'PUT', 'DELETE'}) from None
