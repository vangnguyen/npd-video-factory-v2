"""Inert operator configuration; no GPU request occurs during selection."""
from .backend import DeterministicMockComfyUIBackend, DisabledComfyUIBackend
from .http_backend import ReviewedHTTPComfyUIBackend
from .http_transport import ComfyHTTPTransport


def select_backend(*, environment, registry, job_store, artifacts):
    name = environment.get('COMFYUI_BACKEND', 'disabled').casefold()
    enabled = environment.get('COMFYUI_EXECUTION_ENABLED', 'false').casefold() == 'true'
    if name not in {'disabled', 'mock', 'http'}:
        raise RuntimeError('COMFYUI_BACKEND_INVALID')
    if name == 'mock' and environment.get('APP_ENV', 'development').casefold() == 'production':
        raise RuntimeError('COMFYUI_MOCK_PRODUCTION_FORBIDDEN')
    if not enabled or name == 'disabled':
        return DisabledComfyUIBackend()
    if name == 'mock':
        return DeterministicMockComfyUIBackend()
    try:
        client = ComfyHTTPTransport(origin=environment.get('COMFYUI_API_ORIGIN', ''),
            server_source_sha256=environment.get('COMFYUI_SERVER_SOURCE_SHA256', ''), enabled=True,
            bearer_token=environment.get('COMFYUI_API_TOKEN', ''),
            allowed_http_hosts=tuple(filter(None, environment.get('COMFYUI_ALLOWED_HTTP_HOSTS', '').split(','))))
        return ReviewedHTTPComfyUIBackend(registry=registry, transport=client, job_store=job_store, artifacts=artifacts)
    except (ValueError, TypeError):
        raise RuntimeError('COMFYUI_HTTP_CONFIGURATION_INVALID') from None
