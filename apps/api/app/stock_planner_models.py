"""Read-only stock scheduling DTOs; no provider or publication authorization."""
from typing import Literal
from pydantic import Field
from .models import StrictModel


class StockPlannerAction(StrictModel):
    expected_version: int = Field(ge=1)
    binding_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class StockPlanningRead(StrictModel):
    schema_version: Literal['sql-stock-planner.v1'] = 'sql-stock-planner.v1'
    status: Literal['waiting', 'running', 'succeeded', 'failed', 'cancelled']
    binding_sha256: str
    next_at: float | None
    lease_until: float | None
    completed_searches: int = Field(ge=0)
    total_searches: int = Field(ge=1)
    failed_wire_cycles: dict[str, int]
    error_code: str | None
    retryable: bool
    provider_calls: int = Field(ge=0)
    paid_operations: Literal[0] = 0
    actual_cost_vnd: None = None
    owner_approval_inferred: Literal[False] = False
    publishing_enabled: Literal[False] = False


class StockPlannerHistoryRead(StrictModel):
    event_id: str
    media_plan_id: str
    version: int
    action: str
    evidence: dict
    sha256: str
