"""Local storyboard derivative contracts; no provider or approval authority."""
from typing import Literal
from pydantic import Field, model_validator
from .sql_variant_models import Contract, FamilyVersionRequest, VariantProgressSafety


class DeriveStoryboardRequest(FamilyVersionRequest):
    schema_version: Literal['sql-variant-storyboard-derive.v1'] = 'sql-variant-storyboard-derive.v1'
    member_id: str = Field(pattern=r'^vfm_[a-f0-9]{32}$')
    acknowledge_unapproved_child: Literal[True]

    @model_validator(mode='before')
    @classmethod
    def explicit_ack(cls, value):
        if isinstance(value, dict) and type(value.get('acknowledge_unapproved_child')) is not bool:
            raise ValueError('SQL_VARIANT_EXPLICIT_DRAFT_ACK_REQUIRED')
        return value


class StoryboardDerivationRead(Contract):
    schema_version: Literal['sql-variant-storyboard-receipt.v1'] = 'sql-variant-storyboard-receipt.v1'
    receipt_id: str
    family_id: str
    member_id: str
    workspace_id: str
    state: Literal['pending', 'ready', 'unknown', 'cancelled']
    input_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    result: dict | None
    result_sha256: str | None
    error_code: str | None
    actor_ref: str
    safety: VariantProgressSafety = Field(default_factory=VariantProgressSafety)
