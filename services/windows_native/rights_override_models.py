"""Explicit Owner exceptions, separate from rights verification and publishing approval."""
from typing import Literal
from pydantic import Field,StrictBool,StrictInt
from . import ingestion
from app.models import StrictModel


class OverrideRequest(StrictModel):
    revision:StrictInt=Field(ge=1)
    asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_rights_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    action:Literal['grant','revoke']
    reason:str=Field(min_length=10,max_length=2000)
    evidence_reference:str=Field(min_length=5,max_length=1000)
    valid_days:StrictInt=Field(default=7,ge=1,le=30)
    allow_publishing_review:StrictBool=False
    acknowledged:StrictBool=False
    override_id:str|None=Field(default=None,pattern=r'^nro_[a-f0-9]{32}$')
    expected_override_sha256:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')


class OverrideCreate(OverrideRequest):
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')


class OverrideRecord(StrictModel):
    schema_version:Literal['native-owner-rights-override-v1']
    override_id:str=Field(pattern=r'^nro_[a-f0-9]{32}$')
    workspace_id:str=Field(min_length=1,max_length=100)
    project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    asset_id:str=Field(pattern=r'^[a-f0-9]{32}\.(jpg|png|mp4|wav)$')
    asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    request:OverrideRequest
    actor_ref:str=Field(min_length=1,max_length=100)
    created_at:str
    expires_at:str|None
    rights_independently_verified:Literal[False]
    publishing_authorized:Literal[False]
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
