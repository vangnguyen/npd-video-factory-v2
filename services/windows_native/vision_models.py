"""Native semantic Vision requests remain separate from measured CPU pixel observations."""
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,model_validator
from . import ingestion
from app.models import StrictModel


class NativeVisionRequest(StrictModel):
    schema_version:Literal['native-vision-request-v1']='native-vision-request-v1'
    revision:StrictInt=Field(ge=1)
    observation_ids:list[str]=Field(min_length=1,max_length=16)
    provider_mode:Literal['official','fixture']='official'
    fixture_acknowledged:StrictBool=False
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')

    @model_validator(mode='after')
    def validate_mode(self):
        import re
        if len(set(self.observation_ids))!=len(self.observation_ids) or any(not re.fullmatch('mfo_[a-f0-9]{24}',value) for value in self.observation_ids):
            raise ValueError('NATIVE_VISION_OBSERVATIONS_INVALID')
        if (self.provider_mode=='fixture')!=self.fixture_acknowledged:raise ValueError('NATIVE_VISION_EXPLICIT_FIXTURE_ACK_REQUIRED')
        return self


class NativeVisionAction(StrictModel):
    expected_fingerprint:str=Field(pattern=r'^[a-f0-9]{64}$')
