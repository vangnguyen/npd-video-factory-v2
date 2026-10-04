from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class CanaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner_decision_id: str = Field(pattern=r"^VF-MVP1-[A-Z0-9-]{3,120}$")


class DisabledContentRequest(BaseModel):
    """No Content payload is admitted until a separate integration contract exists."""
    model_config = ConfigDict(extra="forbid", frozen=True)


class BrokerCanaryObservedUsage(BaseModel):
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)
    provider_billing_observed: Literal[False] = False


class CanaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    provider_http_status: int | None = None
    provider: Literal["openai"] = "openai"
    model: Literal["gpt-6-luna"] = "gpt-6-luna"
    returned_model: Literal["gpt-6-luna"] | None = None
    response_status: Literal["completed"] | None = None
    response_id: str | None = None
    safe_openai_request_id: str | None = None
    latency_ms: float = 0
    provider_call_count: Literal[0, 1] = 1
    retries: Literal[0] = 0
    BROKER_CANARY_OBSERVED_USAGE: BrokerCanaryObservedUsage | None = None
