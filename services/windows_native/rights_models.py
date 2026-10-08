"""Versioned human declarations; declaring a license does not verify it."""
from typing import Literal
from pydantic import Field,StrictBool,StrictInt
from . import ingestion
from app.models import StrictModel


class RightsClaim(StrictModel):
    revision:StrictInt=Field(ge=1)
    asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    claimed_source_type:Literal['user_upload','stock','internal_library','ai_generated']
    claimed_rights:Literal['owned','licensed','unknown','restricted']
    license:str|None=Field(default=None,max_length=2000)
    provider:str|None=Field(default=None,max_length=100)
    source_reference:str|None=Field(default=None,max_length=2000)
    creator:str|None=Field(default=None,max_length=200)
    attribution_requirement:str|None=Field(default=None,max_length=1000)
    acknowledged:StrictBool=False


class RightsDeclaration(RightsClaim):
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')


class RightsRecord(StrictModel):
    schema_version:Literal['native-rights-declaration-v1']
    declaration_id:str=Field(pattern=r'^nrd_[a-f0-9]{32}$')
    workspace_id:str=Field(min_length=1,max_length=100)
    project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    asset_id:str=Field(pattern=r'^[a-f0-9]{32}\.(jpg|png|mp4|wav|music\.wav)$')
    asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    request:RightsClaim
    actor_ref:str=Field(min_length=1,max_length=100)
    created_at:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}T.+(?:\+00:00|Z)$')
    verified:Literal[False]
    owner_override_recorded:Literal[False]
    effective_rights_status:Literal['unknown','restricted']
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
