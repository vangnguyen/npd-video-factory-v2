"""Explicit immutable relative assessment requests; no provider or execution grant."""
from typing import Literal
from pydantic import Field,StrictBool,field_validator
from . import ingestion
from app.models import StrictModel
from app.analytics_channel_policy import WinnerChannelPolicy

class Create(StrictModel):
    schema_version:Literal['native-official-winner-request-v1']='native-official-winner-request-v1'
    sync_id:str=Field(pattern=r'^noas_[a-f0-9]{32}$')
    expected_result_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    policy:WinnerChannelPolicy=Field(default_factory=WinnerChannelPolicy)
    acknowledged_recommendation_only:Literal[True]
    acknowledged_protocol_mock:StrictBool=False
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')

    @field_validator('acknowledged_recommendation_only',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('Explicit recommendation-only acknowledgement required')
        return value
