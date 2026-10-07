"""Trusted workspace binding for provider dispatch; no process-wide scope."""
from contextlib import contextmanager
from contextvars import ContextVar

_SCOPE = ContextVar('vf_media_generation_scope', default=None)


@contextmanager
def media_generation_scope(*, workspace_id, project_id, job_id):
    values = (workspace_id, project_id, job_id)
    if any(not isinstance(v, str) or not 1 <= len(v) <= 200 or any(c.isspace() for c in v) for v in values):
        raise ValueError('MEDIA_GENERATION_SCOPE_REQUIRED')
    token = _SCOPE.set(values)
    try:
        yield
    finally:
        _SCOPE.reset(token)


def current_generation_scope():
    value = _SCOPE.get()
    if value is None:
        raise ValueError('MEDIA_GENERATION_SCOPE_REQUIRED')
    return value
