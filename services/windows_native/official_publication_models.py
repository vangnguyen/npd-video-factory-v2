"""Separate scoped official publish intents and consent; never inferred from dry runs."""
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from . import ingestion
from app.models import StrictModel
from app.publishing_models import PublishingTargetBinding
from app.youtube_upload import UNIT,MAX_BODY

class Profile(StrictModel):
    schema_version:Literal['native-official-publishing-profile-v1']='native-official-publishing-profile-v1'
    target:PublishingTargetBinding
    category_id:str=Field(pattern=r'^[0-9]{1,3}$')
    made_for_kids:StrictBool
    contains_synthetic_media:StrictBool
    chunk_size:StrictInt=Field(default=8*1024*1024,ge=UNIT,le=MAX_BODY)
    @model_validator(mode='after')
    def supported(self):
        if self.target.platform!='youtube' or self.target.provider_key!='youtube-data-api-publishing' or self.chunk_size%UNIT:raise ValueError('Explicit supported official publishing profile required')
        return self

class Gates(StrictModel):
    publish_enabled:StrictBool=False
    external_execution_enabled:StrictBool=False
    owner_gate_enabled:StrictBool=False

class Create(StrictModel):
    schema_version:Literal['native-official-publication-request-v1']='native-official-publication-request-v1'
    revision:StrictInt=Field(ge=1)
    dry_run_publication_id:str=Field(pattern=r'^npub_[a-f0-9]{32}$')
    expected_dry_run_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    account_check_id:str=Field(pattern=r'^nack_[a-f0-9]{32}$')
    profile_id:str=Field(pattern=r'^ppf_[A-Za-z0-9_-]{4,60}$')
    expected_configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')

class Approve(StrictModel):
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_official_publication:Literal[True]
    valid_for_seconds:StrictInt=Field(default=900,ge=60,le=3600)
    @field_validator('acknowledged_official_publication',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('Separate explicit official publication consent required')
        return value

class Action(StrictModel):
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

class Renew(Approve):
    expected_dispatch_version:StrictInt=Field(ge=1)
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
