"""Local producer transaction correlation; no Hub or database dependency.

Canonical repositories call capture only at their successful transaction boundary.
Outside an authenticated service command the hook is an inert no-op.
"""
from contextvars import ContextVar
from contextlib import contextmanager

active=ContextVar('vf_service_canonical_outcome',default=None)

@contextmanager
def bind(kind,writer):
    token=active.set((kind,writer))
    try:yield
    finally:active.reset(token)

async def capture(kind,session,value):
    context=active.get()
    if context is None or context[0]!=kind:return False
    await context[1](session,value);return True
