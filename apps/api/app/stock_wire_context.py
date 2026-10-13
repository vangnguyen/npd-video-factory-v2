"""Verified service context for stock operations; no client payload or secret."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import re


@dataclass
class StockWireOperation:
    workspace_id: str
    project_id: str
    source_ref: str
    budget_sha256: str
    wire_attempts: int = 0
    permits: dict | None = None
    cached_inputs: dict | None = None


CURRENT_OPERATION = ContextVar('video_factory_stock_operation', default=None)


@contextmanager
def stock_wire_operation(*, workspace_id, project_id, source_ref, budget_sha256):
    for value in (workspace_id, project_id, source_ref):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', value):
            raise ValueError('STOCK_WIRE_OPERATION_INVALID')
    if not isinstance(budget_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', budget_sha256):
        raise ValueError('STOCK_WIRE_BUDGET_BINDING_INVALID')
    value = StockWireOperation(workspace_id, project_id, source_ref, budget_sha256,
        permits={}, cached_inputs={})
    token = CURRENT_OPERATION.set(value)
    try:
        yield value
    finally:
        CURRENT_OPERATION.reset(token)
