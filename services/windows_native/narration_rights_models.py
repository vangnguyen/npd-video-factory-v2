"""Strict scoped Owner exceptions; never independent model or voice clearance."""
from typing import Literal
from pydantic import Field,StrictBool,StrictInt
from . import ingestion
from app.models import StrictModel

VERSION='native-narration-rights-exception-v1'
class ReviewRequest(StrictModel):
    revision:StrictInt=Field(ge=1)
    narration_job_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    expected_provenance_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    action:Literal['grant','revoke']
    reason:str=Field(min_length=10,max_length=2000)
    evidence_reference:str=Field(min_length=5,max_length=1000)
    valid_days:StrictInt=Field(default=7,ge=1,le=30)
    allow_publishing_review:StrictBool=False
    acknowledged:StrictBool=False
    exception_id:str|None=Field(default=None,pattern=r'^nvr_[a-f0-9]{32}$')
    expected_exception_sha256:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
class ReviewCreate(ReviewRequest):
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
class ReviewRecord(StrictModel):
    schema_version:Literal['native-narration-rights-exception-v1']
    exception_id:str=Field(pattern=r'^nvr_[a-f0-9]{32}$')
    workspace_id:str=Field(min_length=1,max_length=100)
    project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    narration_job_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    provenance:dict
    provenance_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    request:ReviewRequest
    actor_ref:str=Field(min_length=1,max_length=100)
    created_at:str
    expires_at:str|None
    rights_independently_verified:Literal[False]
    speech_quality_accepted:Literal[False]
    publishing_authorized:Literal[False]
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
